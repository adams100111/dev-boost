"""Tracer A — the simplest module shape: a single pkg.install (Homebrew on macOS)."""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula


@register
class Ripgrep(Module):
    name = "ripgrep"
    category = "cli"
    description = "Fast recursive search (rg)."
    profiles = ("cli",)
    per_os = OsMap(macos=BrewFormula("ripgrep"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("rg")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        pkg.install(ctx, "ripgrep")
