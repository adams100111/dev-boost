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
from devboost.exec.primitives import age, pkg, systemd
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
