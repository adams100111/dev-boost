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
from devboost.modules.secrets import age_key, bundle_path
from devboost.passstore import approve as pass_approve
from devboost.passstore import enroll as pass_enroll
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
        return [Check("pass", True, f"no store at {store.root} yet — `devboost install` "
                                    f"clones {pass_paths.pass_repo()}")]
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
    return [Check("pass", True, state), Check("pass-rotation", not todo, rot)]


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


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)
