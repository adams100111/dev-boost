"""Docker — dependency of ddev. Official docker-ce on both OSes (Fedora via Docker's Fedora
repo, replacing the conflicting podman-docker shim; Debian/Ubuntu via Docker's apt repo)."""

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


# Docker CE on Fedora, per Docker's official docs (docs.docker.com/engine/install/fedora).
# Fedora Workstation ships `podman-docker`, which CONFLICTS with docker-ce, so remove it first
# (a deliberate choice to run real Docker consistently with the Ubuntu VPS). `config-manager
# addrepo` is dnf5 (Fedora 41+); the `--add-repo` fallback covers older dnf4.
_DOCKER_CE_FEDORA = (
    "set -e\n"
    "dnf -y install dnf-plugins-core\n"
    "dnf config-manager addrepo --from-repofile"
    " https://download.docker.com/linux/fedora/docker-ce.repo 2>/dev/null"
    " || dnf config-manager --add-repo"
    " https://download.docker.com/linux/fedora/docker-ce.repo\n"
    "dnf -y remove podman-docker || true\n"  # the shim that conflicts with docker-ce
    "dnf -y install docker-ce docker-ce-cli containerd.io"
    " docker-buildx-plugin docker-compose-plugin\n"
)


@register
class Docker(Module):
    name = "docker"
    category = "base"
    description = "Container engine (daemon enabled; invoking user added to docker group)."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        # docker-ce daemon on BOTH Fedora and Debian. On Fedora, the podman-docker shim provides
        # a `docker` command but no daemon — is-enabled(docker.service) is what proves a real
        # engine, so a shim-only box correctly verifies False and gets docker-ce installed.
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
        # docker-ce on both OSes (one engine, consistent with the VPS). `which("dockerd")`
        # distinguishes a real engine already installed from Fedora's podman-docker shim, so the
        # repo setup + install runs only when there's no daemon yet.
        if not ctx.ex.which("dockerd"):
            if ctx.os.family == "debian":
                pkg.install(ctx, *_CE_PKGS, source=_docker_apt_source(ctx))
            else:
                # Fedora: docker-ce from Docker's official repo (removes the conflicting shim).
                ctx.ex.run(["sh", "-c", _DOCKER_CE_FEDORA], sudo=True)
        systemd.enable_system_unit(ctx, "docker.service", now=True)
        user = _invoking_user()
        if user:
            ctx.ex.run(["usermod", "-aG", "docker", user], sudo=True)
