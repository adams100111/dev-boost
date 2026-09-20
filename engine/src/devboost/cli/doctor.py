"""`doctor` — environment preflight in Python (replaces install.sh's dep-ensure).

Subsystem checks (secrets state, mise drift, --gpu) are stubbed here and filled in by
their milestones (M1 secrets, M9 gpu).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from devboost.core.errors import DevbootError
from devboost.exec.primitives import age
from devboost.model import Ctx
from devboost.modules._docker_runtime import rosetta_usable, selected_runtime
from devboost.modules.secrets import age_key, bundle_path
from devboost.passstore import approve as pass_approve
from devboost.passstore import audit as pass_audit
from devboost.passstore import enroll as pass_enroll
from devboost.passstore import notify as pass_notify
from devboost.passstore import paths as pass_paths
from devboost.passstore.layout import Store

# Binaries that must be present on the host before the engine can run.
# Note: jq is NOT used by the Python engine; curl is required (chezmoi, uv, nerd-fonts,
# android tools, claude-code bootstrap all fetch over HTTPS).
_REQUIRED_DEPS = ("curl", "age")

# macOS ships brew + Xcode CLT instead of the Linux package manager. `age` is only needed
# when there is a bundle to decrypt (age.decrypt shells out to the `age` CLI; the key may
# come from the keychain), so it is checked on macOS only when bundle_path() exists.
_REQUIRED_DEPS_MACOS = ("curl", "brew", "xcode-select")

# Minimum free disk space required (in bytes).  A full workstation install uses ~5 GB.
_MIN_FREE_BYTES = 5 * 1024 ** 3  # 5 GiB

# URL used for the network reachability probe (lightweight HEAD request).
_PROBE_URL = "https://fedoraproject.org/"
_PROBE_URL_MACOS = "https://formulae.brew.sh/"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def run_checks(ctx: Ctx, root: Path) -> list[Check]:
    checks: list[Check] = [
        Check("os", ctx.os.distro != "unknown", f"{ctx.os.distro}/{ctx.os.family} {ctx.os.arch}"),
        Check("profiles", (root / "profiles.toml").exists(), str(root / "profiles.toml")),
    ]
    deps: tuple[str, ...] = _REQUIRED_DEPS
    if ctx.os.family == "macos":
        deps = _REQUIRED_DEPS_MACOS + (("age",) if bundle_path().exists() else ())
    for dep in deps:
        checks.append(Check(f"dep:{dep}", ctx.ex.which(dep)))

    # Disk space: use shutil.disk_usage on "/" (pure stdlib, no subprocess needed).
    try:
        free = shutil.disk_usage("/").free
        checks.append(
            Check(
                "disk-space",
                free >= _MIN_FREE_BYTES,
                f"{free // (1024 ** 3)} GiB free (need ≥5 GiB)",
            )
        )
    except OSError as exc:
        checks.append(Check("disk-space", False, str(exc)))

    # Network reachability: a cheap curl --head call (timeout 5 s).
    probe = _PROBE_URL_MACOS if ctx.os.family == "macos" else _PROBE_URL
    net_result = ctx.ex.run([
        "curl", "--head", "--silent", "--connect-timeout", "5",
        "-o", "/dev/null", "-w", "%{http_code}", probe,
    ])
    checks.append(
        Check(
            "network",
            net_result.ok,
            f"HEAD {probe} → exit {net_result.code}",
        )
    )

    # secrets state: 'missing' is a warning (ok), but a present-yet-broken bundle fails.
    # age_key resolves the identity file wherever it lives (configured path, or — on
    # macOS — the login keychain); None means no key anywhere.
    with age_key(ctx) as key:
        state = (
            age.doctor_state(ctx, bundle_path(), key)
            if key is not None
            else ("missing" if not bundle_path().exists() else "cannot-decrypt")
        )
    checks.append(Check("secrets", state in ("ok", "missing"), state))

    checks.extend(_pass_checks(ctx))

    # pi-login: informational only (ok=True) — Pi auth is a manual one-time `pi /login` per box
    # (informational, like the `pass` check — doctor never blocks on it). Surfaces the reminder
    # until auth.json exists.
    auth_json = Path(os.environ["HOME"]) / ".pi" / "agent" / "auth.json"
    if auth_json.exists():
        pi_detail = "Pi authenticated (~/.pi/agent/auth.json present)"
    elif ctx.ex.which("harness") or ctx.ex.which("pi"):
        pi_detail = "Pi installed but not authenticated — run `pi /login` once per box"
    else:
        pi_detail = "Pi not installed (install the `pi` profile)"
    checks.append(Check("pi-login", True, pi_detail))

    if ctx.os.family == "macos":
        checks.append(_permissions_check(ctx))
        checks.append(_rosetta_check(ctx))
        from devboost.cli import doctor_desktop  # local: it imports Check from here
        checks += doctor_desktop.checks(ctx)
        checks.append(_docker_runtime_check(ctx))
    return checks


def _pass_checks(ctx: Ctx) -> list[Check]:
    """pass: enrollment state (informational) + rotation backlog after a revoke (blocking).

    Never raises: a bad config, a failing gpg or a malformed store file is a failing check.
    """
    try:
        return _pass_state(ctx)
    except (DevbootError, OSError) as exc:
        return [Check("pass", False, str(exc))]


def _pass_state(ctx: Ctx) -> list[Check]:
    store = Store(pass_paths.store_dir())
    if not store.is_clone():
        repo = pass_paths.pass_repo()
        where = f"clones {repo}" if repo else "needs `pass_repo` set (devboost pass status)"
        return [Check("pass", True, f"no store at {store.root} yet — `devboost install` {where}")]
    device = pass_paths.device_name()
    acc = pass_enroll.local_access(ctx, store, device)
    name = acc.record.name if acc.record else device
    state = {
        "enrolled": f"{name} is enrolled",
        "pending": f"{name} is waiting for approval — on an enrolled device: "
                   f"devboost pass approve {name}",
        "new": "this device is not enrolled — run `devboost pass enroll`",
        "genesis": "the store is empty — run `devboost pass enroll` to initialise it",
        "no-store": "no store",
    }[acc.state]
    todo = pass_approve.unrotated(ctx, store)
    rot = ("nothing awaiting rotation" if not todo else
           f"{len(todo)} entries are still readable by a revoked device's key (git history) "
           "— rotate each with `pass edit <entry>`: "
           + ", ".join(f"{u.entry} ({u.device})" for u in todo))
    return [Check("pass", True, state), Check("pass-rotation", not todo, rot),
            _recipients_check(ctx, store)]


def _recipients_check(ctx: Ctx, store: Store) -> Check:
    """A failing audit (e.g. a push-controlled malformed `.gpg-id`) must not collapse the
    healthy `pass` / `pass-rotation` checks above it — only this one fails."""
    p = pass_notify.printable
    try:
        report = pass_audit.audit(ctx, store)
    except (DevbootError, OSError) as exc:
        return Check("pass-recipients", False, str(exc))
    if report.mismatches:
        rec = (f"{len(report.mismatches)} entries are not encrypted to exactly their .gpg-id "
               "keys — " + "; ".join(f"{p(m.entry)}: {p(pass_audit.fix_hint(store, m))}"
                                     for m in report.mismatches))
    else:
        rec = "every entry is encrypted to exactly its .gpg-id keys"
    if report.unauditable:
        rec += (f" (not checked — .gpg-id names keys by email: "
                f"{', '.join(p(f) for f in report.unauditable)})")
    return Check("pass-recipients", not report.mismatches, rec)


def _permissions_check(ctx: Ctx) -> Check:
    """Informational: privacy grants the user still has to give (see `devboost permissions`)."""
    from devboost.core.registry import load
    from devboost.exec.primitives import tcc

    missing = [
        f"{name}: {g.app} → {tcc.label(g.service)}"
        for name, cls in sorted(load().items())
        if cls.tcc and cls().verify(ctx)
        for g in tcc.pending(name, cls.tcc)
    ]
    detail = "; ".join(missing) + " — run `devboost permissions`" if missing else "all granted"
    return Check("permissions", True, detail)


def _rosetta_check(ctx: Ctx) -> Check:
    """Informational: Rosetta state; from macOS 28 the Intel-only apps that stop working."""
    from devboost.modules import macos

    if macos.rosetta_supported(ctx.os):
        if macos.rosetta_present(ctx):
            return Check("rosetta", True, "installed")
        why = "Intel-only apps, fast amd64 containers"
        return Check("rosetta", True, f"not installed — `devboost install rosetta` ({why})")
    apps = macos.intel_only_apps(ctx)
    if apps is None:
        found = "could not list Intel-only apps (system_profiler failed)"
    elif apps:
        found = f"Intel-only apps that will not run: {', '.join(apps)}"
    else:
        found = "no Intel-only apps found"
    return Check(
        "rosetta", True, f"macOS {ctx.os.version_id} limits Rosetta to legacy games; {found}"
    )


def _apple_m4_or_m5(ctx: Ctx) -> bool:
    """True on an Apple M4/M5 chip (``sysctl -n machdep.cpu.brand_string``, e.g. "Apple M4 Pro").

    Read-only probe; a failed sysctl (unlikely, but not a hard requirement here) is just
    treated as "not M4/M5" rather than raised.
    """
    res = ctx.ex.run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return res.ok and any(f"Apple M{n}" in res.stdout for n in (4, 5))


def _docker_runtime_check(ctx: Ctx) -> Check:
    """macOS: the selected Docker runtime answers on its context (spec §8)."""
    try:
        rt = selected_runtime()
    except DevbootError as exc:
        return Check("docker-runtime", False, str(exc))
    if not rt.installed(ctx):
        return Check("docker-runtime", True, f"{rt.name} not installed (devboost install docker)")
    ok = rt.verify(ctx)
    detail = (
        f"{rt.name} (context {rt.context_name}) healthy"
        if ok
        else f"{rt.name} engine not reachable on context {rt.context_name} — "
        "run: devboost install docker"
    )
    if rt.name == "colima" and not rosetta_usable(ctx):
        # `rosetta_usable` is exactly what decides Colima's --vz-rosetta (M4-D8): from
        # macOS 28, Rosetta may be installed yet unusable for Linux containers.
        detail += "; Rosetta unavailable — amd64 images run under qemu (slower)"
    if not ok and _apple_m4_or_m5(ctx):
        # M4-D20 carry-over: SME on Apple M4/M5 chips can crash .NET 10 guests with
        # SIGILL (exit 132). No env-var workaround is confirmed to fix this — a real
        # fix needs a patched .NET 10 image/SDK (dotnet/runtime#122608, #133030; both
        # `DOTNET_EnableArm64Sve=0` and `GLIBC_TUNABLES=glibc.cpu.name=generic` were
        # tried and did NOT work, because the probe is in the native runtime, not
        # JIT-gated) — so do not invent a flag here. Only on a check that FAILED: a
        # healthy runtime needs no troubleshooting hint.
        detail += ("; Apple M4/M5: if .NET containers exit with 132 (SIGILL), "
                   "update the .NET 10 image/SDK to the latest patch")
    return Check("docker-runtime", ok, detail)


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)
