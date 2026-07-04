"""server profile — headless-VPS hardening + ops (Ubuntu/Debian focus).

dev-boost's `system` tier is Fedora-desktop-shaped (btrfs/snapper/dnf-automatic); a
remote Linux VPS needs a different set: a host firewall, compressed swap, a mesh VPN.
These modules target the Debian/Ubuntu family (the common VPS base) and gate off
elsewhere rather than silently no-op.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import SecretsError, UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import age, pkg, systemd, usermgmt
from devboost.model import Ctx, Module
from devboost.modules.secrets import Secrets, bundle_path, key_path


def _secret(ctx: Ctx, field: str) -> str | None:
    """Read one field from the age secrets bundle, or None if unavailable.

    Server modules must not fail `devboost server` just because an optional secret
    (a Tailscale auth key, B2 credentials) wasn't provisioned — they degrade to a
    printed next-step instead.
    """
    try:
        data = age.decrypt(ctx, bundle_path(), key_path())
    except SecretsError:
        return None
    return data.get(field)


@register
class Tailscale(Module):
    name = "tailscale"
    category = "server"
    description = "Tailscale mesh VPN + Tailscale SSH (unattended via a secrets auth-key)."
    profiles = ("server",)
    requires = (Secrets,)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("tailscale")

    def install(self, ctx: Ctx) -> None:
        # Official cross-distro installer (same curl|sh escape hatch as chezmoi/starship).
        if not ctx.ex.which("tailscale"):
            ctx.ex.run(["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"])
        # Bring the node up with Tailscale SSH when we have an auth key; otherwise leave
        # the one-time interactive `tailscale up` to the operator — never block install.
        key = _secret(ctx, "TAILSCALE_AUTHKEY")
        if key:
            ctx.ex.run(["tailscale", "up", "--ssh", f"--authkey={key}"], sudo=True)
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
    profiles = ("server",)

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


@register
class ResticB2(Module):
    name = "restic-b2"
    category = "server"
    description = "Offsite encrypted backups — restic → Backblaze B2, nightly systemd timer."
    profiles = ("server",)
    requires = (Secrets,)

    def verify(self, ctx: Ctx) -> bool:
        d = systemd._user_unit_dir()
        if not ((d / "restic-b2.service").exists() and (d / "restic-b2.timer").exists()):
            return False
        return systemd.is_enabled(ctx, "restic-b2.timer", user=True)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("restic"):
            pkg.install(ctx, "restic")
        # Destination + credentials come from the age bundle. Without them we can't run an
        # offsite backup, so install the binary and stop — don't wire a timer to nowhere.
        b2_id = _secret(ctx, "B2_ACCOUNT_ID")
        b2_key = _secret(ctx, "B2_ACCOUNT_KEY")
        repo = _secret(ctx, "RESTIC_REPOSITORY")
        password = _secret(ctx, "RESTIC_PASSWORD")
        if not (b2_id and b2_key and repo and password):
            log.warn(
                "restic-b2: installed restic, but B2/restic secrets are missing — add "
                "B2_ACCOUNT_ID, B2_ACCOUNT_KEY, RESTIC_REPOSITORY, RESTIC_PASSWORD to the "
                "secrets bundle to enable the nightly timer"
            )
            return
        d = _devboost_dir()
        d.mkdir(parents=True, exist_ok=True)
        include = d / "restic-include"
        if not include.exists():  # editable default; keep what the user tuned
            home = Path(os.environ["HOME"])
            include.write_text(f"{home}/repos\n{home}/.config\n", encoding="utf-8")
        # Secrets live in a 0600 EnvironmentFile, never inline in the unit.
        envfile = d / "restic-b2.env"
        envfile.write_text(
            f"B2_ACCOUNT_ID={b2_id}\nB2_ACCOUNT_KEY={b2_key}\n"
            f"RESTIC_REPOSITORY={repo}\nRESTIC_PASSWORD={password}\n",
            encoding="utf-8",
        )
        envfile.chmod(0o600)
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
