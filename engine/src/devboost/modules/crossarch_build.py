"""crossarch-build — capped rootless multi-arch builds for the brain (podman + qemu binfmt).

Installs podman (daemonless, first-class rootless — coexists with docker-ce; only the
podman-docker CLI shim conflicts, which docker.py already removes) and qemu-user-static so
`podman build --platform linux/amd64,linux/arm64 --manifest ... --push` runs as the capped
`devbrain` user without root or the docker group. binfmt handlers register via the
qemu-user-static package (Debian also gets binfmt-support).
"""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class CrossArchBuild(Module):
    name = "crossarch-build"
    category = "brain-host"
    description = "Rootless podman + qemu binfmt for capped multi-arch (amd64+arm64) builds."
    profiles = ("brain-host",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("podman")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "podman", "qemu-user-static")
        # Debian's qemu-user-static needs binfmt-support to register the arm64 handler.
        if ctx.os.family == "debian":
            pkg.install(ctx, "binfmt-support")
