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

    def _podman_path(self, ctx: Ctx) -> bool:
        # Fedora with NO real Docker daemon. A `dockerd` binary means real Docker (docker-ce /
        # moby) is installed out-of-band — the podman-docker shim never provides `dockerd` — so
        # we respect it via the daemon path instead of installing podman (which would conflict).
        return ctx.os.family != "debian" and not ctx.ex.which("dockerd")

    def verify(self, ctx: Ctx) -> bool:
        if self._podman_path(ctx):
            return ctx.ex.which("podman") and systemd.is_enabled(ctx, "podman.socket", user=True)
        # Real Docker daemon (Fedora docker-ce installed out-of-band, or Debian docker-ce).
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
        if self._podman_path(ctx):
            # Fedora Workstation is Podman-native — it ships `podman` + the `podman-docker`
            # shim, which CONFLICTS with `moby-engine`/`docker-ce`. Don't fight the distro: use
            # rootless Podman as the engine ddev/Aspire talk to (DOCKER_HOST wired in .bashrc).
            pkg.install(ctx, "podman", "podman-docker")
            systemd.enable_user_unit(ctx, "podman.socket", now=True)
            return
        # Real Docker daemon: Debian docker-ce, OR a pre-existing docker-ce on Fedora we respect
        # (we never install podman-docker over it, and never pass --allowerasing, so it's kept).
        # Debian: add the repo + install only when docker is absent (re-adding
        # download.docker.com would conflict on an existing docker.asc Signed-By).
        if ctx.os.family == "debian" and not ctx.ex.which("docker"):
            pkg.install(ctx, *_CE_PKGS, source=_docker_apt_source(ctx))
        systemd.enable_system_unit(ctx, "docker.service", now=True)
        user = _invoking_user()
        if user:
            ctx.ex.run(["usermod", "-aG", "docker", user], sudo=True)
