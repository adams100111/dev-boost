"""Docker — dependency of ddev (Fedora: moby-engine; Debian/Ubuntu: official docker-ce)."""

from __future__ import annotations

import os

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg, systemd
from devboost.model import AptRepo, Ctx, Module

#: Docker's official engine package set on Debian/Ubuntu. `docker.io` (Ubuntu's own
#: package) is deliberately NOT used — Docker's docs list it as a *conflicting*
#: package, so installing it on a box with the docker-ce repo fails.
_CE_PKGS = (
    "docker-ce", "docker-ce-cli", "containerd.io",
    "docker-buildx-plugin", "docker-compose-plugin",
)


def _docker_apt_source(ctx: Ctx) -> pkg.Source:
    """Docker's official apt repo for the running Ubuntu release (suite = codename)."""
    return OsMap(
        debian=AptRepo(
            list_line=(
                "deb [arch=amd64,arm64"
                " signed-by=/etc/apt/keyrings/download-docker-com.gpg]"
                f" https://download.docker.com/linux/ubuntu {ctx.os.codename} stable"
            ),
            key_url="https://download.docker.com/linux/ubuntu/gpg",
        )
    )


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
        if ctx.os.family == "debian":
            # Skip the repo-add + install when Docker is already present (e.g. set up
            # out-of-band): re-adding download.docker.com would conflict with an existing
            # docker.asc Signed-By. Still (re)enable the daemon and fix the group below.
            if not ctx.ex.which("docker"):
                # Official docker-ce set from Docker's own apt repo.
                pkg.install(ctx, *_CE_PKGS, source=_docker_apt_source(ctx))
        else:
            # Fedora ships the daemon as moby-engine.
            pkg.install(ctx, "moby-engine")
        systemd.enable_system_unit(ctx, "docker.service", now=True)
        user = _invoking_user()
        if user:
            ctx.ex.run(["usermod", "-aG", "docker", user], sudo=True)
