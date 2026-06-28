"""Docker — dependency of ddev (Fedora: moby-engine; Debian/Ubuntu: docker.io)."""

from __future__ import annotations

import os

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg, systemd
from devboost.model import Ctx, Module


def _invoking_user() -> str:
    """Return the real (non-root) user; prefers SUDO_USER over USER."""
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


@register
class Docker(Module):
    name = "docker"
    category = "base"
    description = "Container engine (daemon enabled; invoking user added to docker group)."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("docker"):
            return False
        if not systemd.is_enabled(ctx, "docker.service"):
            return False
        user = _invoking_user()
        if user:
            res = ctx.ex.run(["id", "-nG", user])
            if not res.ok or "docker" not in res.stdout.split():
                return False
        return True

    def install(self, ctx: Ctx) -> None:
        # Fedora ships the daemon as moby-engine; Debian/Ubuntu as docker.io (universe).
        pkg.install(ctx, OsMap(fedora="moby-engine", debian="docker.io"))
        systemd.enable_system_unit(ctx, "docker.service", now=True)
        user = _invoking_user()
        if user:
            ctx.ex.run(["usermod", "-aG", "docker", user], sudo=True)
