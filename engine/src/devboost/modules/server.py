"""server profile — headless-VPS hardening + ops (Ubuntu/Debian focus).

dev-boost's `system` tier is Fedora-desktop-shaped (btrfs/snapper/dnf-automatic); a
remote Linux VPS needs a different set: a host firewall, compressed swap, a mesh VPN.
These modules target the Debian/Ubuntu family (the common VPS base) and gate off
elsewhere rather than silently no-op.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import NeedsUser, PresentUnmanaged, SecretsError, UnsupportedOS
from devboost.core.osinfo import LINUX_FAMILIES, OsMap
from devboost.core.registry import register
from devboost.exec.primitives import age, pkg, systemd, usermgmt
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask
from devboost.modules._credentials import is_interactive
from devboost.modules._launchd_jobs import job_scheduled, schedule_job
from devboost.modules.macos import Homebrew
from devboost.modules.secrets import age_key, bundle_path


def _secret(ctx: Ctx, field: str) -> str | None:
    """Read one field from the age secrets bundle, or None if unavailable.

    Server modules must not fail `devboost server` just because an optional secret
    (a Tailscale auth key, B2 credentials) wasn't provisioned — they degrade to a
    printed next-step instead. The key comes from `age_key`: the key file, or on macOS the
    login keychain (M1), materialized 0600 only for the decrypt; off macOS it is exactly
    the configured key path, as before.
    """
    with age_key(ctx) as key:
        if key is None:
            return None
        try:
            data = age.decrypt(ctx, bundle_path(), key)
        except SecretsError:
            return None
    return data.get(field)


_TS_APP = Path("/Applications/Tailscale.app")
_TS_APP_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
_TS_CASK = BrewCask("tailscale-app")
#: Tailscale KB 1080: on macOS the CLI is the app binary, called by its real path. A
#: wrapper keeps that path (a symlink would not) and works in scripts, unlike an alias.
_TS_WRAPPER = (
    "#!/bin/sh\n"
    "# devboost — the Tailscale app's CLI. Managed by dev-boost (tailscale module).\n"
    f'exec "{_TS_APP_BIN}" "$@"\n'
)


def ts_cli() -> Path:
    return Path(os.environ["HOME"]) / ".local" / "bin" / "tailscale"


@contextmanager
def _auth_key_file(key: str) -> Iterator[str]:
    """The auth key as a ``--auth-key`` value that keeps it off argv (``ps`` shows argv).

    The key goes to a 0600 file in a private (0700) temp dir, removed afterwards; the
    Tailscale CLI documents ``--auth-key=file:<path>`` as "a path to a file containing the
    auth key". The CLI reads it itself, before it talks to the daemon, so the file is the
    invoking user's even when `tailscale up` runs under sudo (root can read it).
    """
    tmp = Path(tempfile.mkdtemp(prefix="devboost-tailscale-"))
    try:
        path = tmp / "authkey"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        yield f"--auth-key=file:{path}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ts_app_running(ctx: Ctx) -> bool:
    """Whether the Tailscale app is running. On macOS the CLI is the app binary, so
    `status` against a stopped app may start the GUI — a probe must never do that."""
    return ctx.ex.run(["pgrep", "-x", "Tailscale"]).ok


def _ts_state(ctx: Ctx) -> str:
    """BackendState from `tailscale status --json` ("Running", "NeedsLogin", …); "" if none
    — also when the app is not running, which is never started just to ask."""
    if not _ts_app_running(ctx):
        return ""
    res = ctx.ex.run([str(ts_cli()), "status", "--json"])
    try:
        data = json.loads(res.stdout) if res.stdout.strip() else None
    except ValueError:
        return ""
    state = data.get("BackendState") if isinstance(data, dict) else None
    return state if isinstance(state, str) else ""


def _ensure_wrapper(cli: Path) -> None:
    """Write the CLI wrapper when the path is free or already ours; never touch anything
    else there (a symlink to the app binary, the user's own script) — that is the user's."""
    want = _TS_WRAPPER.encode("utf-8")
    if cli.is_symlink() or (cli.exists() and (not cli.is_file() or cli.read_bytes() != want)):
        log.skip(f"tailscale: {cli} is not dev-boost's wrapper — left as it is")
        return
    if not cli.exists():
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_bytes(want)
    cli.chmod(0o755)  # also repairs a managed wrapper that lost its exec bit


@dataclass(frozen=True)
class _TailscaleMac:
    """macOS: the standalone app (cask `tailscale-app`), its CLI on PATH, and the one-time
    approval only the user can give. The Mac is a fleet client: no Tailscale SSH server.

    A hand-installed Tailscale.app that brew cannot adopt (PresentUnmanaged) is left as it
    is, but still gets the CLI wrapper and the connection check (ruling R6)."""

    uses_brew: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        return (
            (_TS_CASK.verify(ctx) or _TS_APP.is_dir())
            and ts_cli().is_file()
            and _ts_state(ctx) == "Running"
        )

    def install(self, ctx: Ctx) -> None:
        # The cask is a .pkg: brew cannot --adopt it and would re-run the installer over a
        # hand-installed app, so an app brew does not manage is left as it is (C-R21).
        if _TS_APP.is_dir() and not _TS_CASK.verify(ctx):
            log.skip(f"tailscale: {_TS_APP} was installed outside Homebrew — left as it is")
        else:
            try:
                _TS_CASK.install(ctx)
            except PresentUnmanaged:
                if not _TS_APP.is_dir():
                    raise
                log.skip(f"tailscale: {_TS_APP} was installed outside Homebrew — left as it is")
        cli = ts_cli()
        _ensure_wrapper(cli)
        state = _ts_state(ctx)
        if state == "Running":
            return
        key = _secret(ctx, "TAILSCALE_AUTHKEY")
        if key and state == "NeedsLogin":
            with _auth_key_file(key) as auth_arg:
                joined = ctx.ex.run([str(cli), "up", auth_arg]).ok
            if joined:
                return
            raise NeedsUser(
                "the TAILSCALE_AUTHKEY in the secrets bundle was rejected (expired or revoked)",
                "create a new auth key in the Tailscale admin console and update the secrets "
                "bundle, or sign in from the Tailscale menu bar app",
            )
        approve = (
            "allow its VPN configuration when macOS asks (System Settings → General → "
            "Login Items & Extensions → Network Extensions), then sign in — or add "
            "TAILSCALE_AUTHKEY to the secrets bundle"
        )
        if not is_interactive():
            # Launching the app pops macOS's VPN / extension prompt: never on an unwatched
            # desktop (global constraint), so the user opens it themselves.
            raise NeedsUser(
                "Tailscale is installed but not connected — open Tailscale and approve it",
                f"open Tailscale from Applications, {approve}",
            )
        ctx.ex.run(["open", "-a", "Tailscale"])
        raise NeedsUser(
            "Tailscale is installed but not connected",
            f"open Tailscale from the menu bar, {approve}",
        )


@register
class Tailscale(Module):
    name = "tailscale"
    category = "server"
    description = "Tailscale mesh VPN + Tailscale SSH (unattended via a secrets auth-key)."
    profiles = ("server", "remote")
    requires = (Homebrew,)
    per_os = OsMap(macos=_TailscaleMac())
    # The tailscale-app cask is a .pkg, which brew installs with sudo (C-R21).
    needs_sudo_on_macos: ClassVar[bool] = True
    # No hard `requires = (Secrets,)`: these read secrets OPTIONALLY via _secret (which
    # degrades to None when the bundle is absent). A hard require would let a missing
    # bundle *block* them entirely (defeating the graceful path) — see _secret's docstring.

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("tailscale")

    def sudo_needed(self, ctx: Ctx) -> bool:
        if ctx.os.family != "macos":
            return super().sudo_needed(ctx)
        # Only the .pkg cask needs root: when it is not installed and no app is there,
        # or, under --force, when brew would upgrade it. Connecting and approving never
        # need a password, so an installed-but-unapproved Tailscale does not ask for one.
        managed = _TS_CASK.verify(ctx)
        if ctx.force and managed:
            return True
        return not managed and not _TS_APP.is_dir()

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # Official cross-distro installer (same curl|sh escape hatch as chezmoi/starship).
        if not ctx.ex.which("tailscale"):
            ctx.ex.run(["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"])
        # Bring the node up with Tailscale SSH when we have an auth key; otherwise leave
        # the one-time interactive `tailscale up` to the operator — never block install.
        key = _secret(ctx, "TAILSCALE_AUTHKEY")
        if key:
            with _auth_key_file(key) as auth_arg:
                ctx.ex.run(["tailscale", "up", "--ssh", auth_arg], sudo=True)
        else:
            log.warn(
                "tailscale: no TAILSCALE_AUTHKEY in secrets — "
                "run `sudo tailscale up --ssh` once to join the tailnet"
            )


@register
class ServerFirewall(Module):
    name = "server-firewall"
    category = "server"
    description = "ufw baseline: deny incoming, allow SSH + tailscale0; disable exposed rpcbind."
    profiles = ("server",)
    families: ClassVar[tuple[str, ...]] = ("debian",)

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("ufw"):
            return False
        return "Status: active" in ctx.ex.run(["ufw", "status"], sudo=True).stdout

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "debian":
            raise UnsupportedOS(
                f"server-firewall uses ufw (Debian/Ubuntu); detected {ctx.os.distro!r} "
                "(Fedora ships firewalld)"
            )
        pkg.install(ctx, "ufw")
        # A baseline that CANNOT lock you out: deny inbound, but explicitly keep SSH and
        # open the tailnet interface. Dropping public :22 (relying on Tailscale SSH) is a
        # deliberate follow-up the operator does AFTER confirming tailnet access — not here.
        for rule in (
            ["default", "deny", "incoming"],
            ["default", "allow", "outgoing"],
            ["allow", "OpenSSH"],
            ["allow", "in", "on", "tailscale0"],
        ):
            ctx.ex.run(["ufw", *rule], sudo=True)
        ctx.ex.run(["ufw", "--force", "enable"], sudo=True)
        # rpcbind was found listening on 0.0.0.0:111 — not needed on a dev VPS and a
        # classic exposure. Disable + mask (reversible; keeps the package for NFS users).
        ctx.ex.run(
            ["systemctl", "disable", "--now", "rpcbind.socket", "rpcbind.service"], sudo=True
        )
        ctx.ex.run(["systemctl", "mask", "rpcbind.socket"], sudo=True)


@register
class Zram(Module):
    name = "zram"
    category = "server"
    description = "Compressed-RAM swap (zstd, ~half RAM) — OOM insurance for long builds/agents."
    profiles = ("server",)
    # Linux compressed swap
    families: ClassVar[tuple[str, ...]] = LINUX_FAMILIES

    def _conf(self, ctx: Ctx) -> str:
        override = os.environ.get("DEVBOOST_ZRAM_CONF")
        if override:
            return override
        if ctx.os.family == "debian":
            return "/etc/default/zramswap"
        return "/etc/systemd/zram-generator.conf"

    def verify(self, ctx: Ctx) -> bool:
        return Path(self._conf(ctx)).exists()

    def install(self, ctx: Ctx) -> None:
        conf = self._conf(ctx)
        if ctx.os.family == "debian":
            pkg.install(ctx, "zram-tools")
            body = "# devboost — managed\nALGO=zstd\nPERCENT=50\nPRIORITY=100\n"
            ctx.ex.run(["tee", conf], sudo=True, stdin=body)
            systemd.enable_system_unit(ctx, "zramswap.service", now=True)
        else:
            pkg.install(ctx, "zram-generator")
            body = (
                "# devboost — managed\n[zram0]\nzram-size = ram / 2\n"
                "compression-algorithm = zstd\n"
            )
            ctx.ex.run(["tee", conf], sudo=True, stdin=body)
            ctx.ex.run(["systemctl", "start", "systemd-zram-setup@zram0.service"], sudo=True)


def _current_user() -> str:
    for var in ("SUDO_USER", "USER", "LOGNAME"):
        v = os.environ.get(var)
        if v and v != "root":
            return v
    return os.environ.get("USER") or "root"


@register
class AgentSudo(Module):
    name = "agent-sudo"
    category = "server"
    description = "Passwordless sudo for your user — so agents/automation never hang on a prompt."
    profiles = ()
    # passwordless sudo for agents on a server/brain
    families: ClassVar[tuple[str, ...]] = LINUX_FAMILIES

    def verify(self, ctx: Ctx) -> bool:
        # True only if sudo works non-interactively AND our drop-in is what enables it.
        # `sudo -n` never prompts (it fails fast if a password would be needed), so this
        # never hangs; the file check neutralises a still-valid sudo timestamp.
        path = usermgmt.sudoers_path(_current_user())
        return ctx.ex.run(["sudo", "-n", "test", "-f", path]).ok

    def install(self, ctx: Ctx) -> None:
        # NOPASSWD for the invoking user, written through the visudo-validated staging path
        # (a bad rule is rejected, never left in place). The FIRST run needs one interactive
        # sudo to write the drop-in (chicken-and-egg); every agent sudo afterward is silent.
        # Fits dev-boost's model: a personal box you own, reached only over the tailnet.
        user = _current_user()
        content = usermgmt.sudoers_content(user, "nopasswd", ())
        if content is None:  # unreachable for "nopasswd"; keeps the type honest
            return
        usermgmt.write_sudoers(ctx, user, content)


def _devboost_dir() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "devboost"


_B2_FIELDS = ("B2_ACCOUNT_ID", "B2_ACCOUNT_KEY", "RESTIC_REPOSITORY", "RESTIC_PASSWORD")
_B2_JOB = "restic-b2"

#: The macOS job: the Linux unit's ExecStartPre=- / ExecStart / ExecStartPost, in sh.
B2_MAC_SCRIPT = (
    'set -a; . "$HOME/.config/devboost/restic-b2.env"; set +a; '
    "restic init >/dev/null 2>&1; "
    'restic backup --files-from "$HOME/.config/devboost/restic-include" && '
    "restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune"
)


def _write_private(path: Path, text: str) -> None:
    """Replace ``path`` with ``text``, readable by the owner only, atomically.

    The content goes to a fresh 0600 temp file in the same directory (``mkstemp`` uses
    O_EXCL, so it never opens an existing file or follows a link), is fsynced, then
    renamed over ``path``. There is no moment when the secrets sit in a looser file, a
    reader never sees a half-written one, and a symlink planted at ``path`` is replaced
    rather than written through.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        Path(tmp).unlink(missing_ok=True)
        raise


def _b2_prepare(ctx: Ctx, *, shell_quoted: bool = False) -> Path:
    """Write restic-include (once) and the 0600 env file.

    A missing secret raises ``NeedsUser`` (the run reports ``blocked`` with the fix) rather
    than returning quietly into a verify that must fail (final review I2).

    ``shell_quoted`` quotes values for ``sh`` to source (macOS); systemd's
    EnvironmentFile format (Linux) is unchanged. Secrets live only in this file, never
    in a unit, a plist or an argv.
    """
    values: dict[str, str] = {}
    for field in _B2_FIELDS:
        value = _secret(ctx, field)
        if not value:
            raise NeedsUser(
                "restic-b2: restic is installed, but the B2/restic secrets are missing",
                "add B2_ACCOUNT_ID, B2_ACCOUNT_KEY, RESTIC_REPOSITORY and RESTIC_PASSWORD "
                "to the secrets bundle, then re-run",
            )
        values[field] = value
    d = _devboost_dir()
    d.mkdir(parents=True, exist_ok=True)
    include = d / "restic-include"
    if not include.exists():  # editable default; keep what the user tuned
        home = Path(os.environ["HOME"])
        include.write_text(f"{home}/repos\n{home}/.config\n", encoding="utf-8")
    envfile = d / "restic-b2.env"
    _write_private(
        envfile,
        "".join(f"{k}={shlex.quote(v) if shell_quoted else v}\n" for k, v in values.items()),
    )
    return envfile


@dataclass(frozen=True)
class _MacResticB2:
    """macOS: brew restic; with secrets, a nightly launchd agent (plan D7).

    The agent sources the 0600 env file at run time, so no secret is in its plist.
    """

    uses_brew: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.installed(ctx, "restic")
            and (_devboost_dir() / "restic-b2.env").is_file()
            and job_scheduled(ctx, _B2_JOB, B2_MAC_SCRIPT, "daily")
        )

    def install(self, ctx: Ctx) -> None:
        if not pkg.installed(ctx, "restic"):
            pkg.install(ctx, "restic")
        _b2_prepare(ctx, shell_quoted=True)
        schedule_job(ctx, _B2_JOB, B2_MAC_SCRIPT, "daily")


@register
class ResticB2(Module):
    name = "restic-b2"
    category = "server"
    description = (
        "Offsite encrypted backups — restic → Backblaze B2, nightly "
        "(systemd timer / launchd agent)."
    )
    profiles = ("server",)
    requires = (Homebrew,)  # macOS brews restic (M4-D9); Linux plans drop Homebrew
    per_os = OsMap(macos=_MacResticB2())
    # No hard `requires = (Secrets,)`: these read secrets OPTIONALLY via _secret (which
    # degrades to None when the bundle is absent). A hard require would let a missing
    # bundle *block* them entirely (defeating the graceful path) — see _secret's docstring.

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        d = systemd._user_unit_dir()
        if not ((d / "restic-b2.service").exists() and (d / "restic-b2.timer").exists()):
            return False
        return systemd.is_enabled(ctx, "restic-b2.timer", user=True)

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        if not ctx.ex.which("restic"):
            pkg.install(ctx, "restic")
        # Destination + credentials come from the age bundle. Without them we can't run an
        # offsite backup, so install the binary and stop (blocked, with the fix) — don't
        # wire a timer to nowhere.
        envfile = _b2_prepare(ctx)
        include = envfile.parent / "restic-include"
        service = (
            "[Unit]\nDescription=devboost restic → B2 backup\n\n[Service]\nType=oneshot\n"
            f"EnvironmentFile={envfile}\n"
            "ExecStartPre=-/usr/bin/restic init\n"  # no-op once the repo exists
            f"ExecStart=/usr/bin/restic backup --files-from {include}\n"
            "ExecStartPost=/usr/bin/restic forget --keep-daily 7 --keep-weekly 4 "
            "--keep-monthly 6 --prune\n"
        )
        timer = (
            "[Unit]\nDescription=nightly restic → B2\n\n[Timer]\nOnCalendar=daily\n"
            "Persistent=true\n\n[Install]\nWantedBy=timers.target\n"
        )
        systemd.write_user_unit(ctx, "restic-b2.service", service)
        systemd.write_user_unit(ctx, "restic-b2.timer", timer)
        systemd.enable_user_unit(ctx, "restic-b2.timer", now=True)
