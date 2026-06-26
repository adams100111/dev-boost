"""Docker — dependency of ddev; uniform pkg install (Fedora: moby-engine)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class Docker(Module):
    name = "docker"
    category = "base"
    description = "Container engine."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("docker")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "moby-engine")
