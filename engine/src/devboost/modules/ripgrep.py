"""Tracer A — the simplest module shape: a single pkg.install."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class Ripgrep(Module):
    name = "ripgrep"
    category = "cli"
    description = "Fast recursive search (rg)."
    profiles = ("cli",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("rg")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "ripgrep")
