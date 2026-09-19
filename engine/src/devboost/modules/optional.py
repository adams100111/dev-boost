"""optional-editors profile (opt-in, off the production path)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules.macos import Homebrew


@register
class Neovim(Module):
    name = "neovim"
    category = "optional-editors"
    description = "Neovim editor."
    profiles = ("optional-editors",)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewFormula("neovim"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("nvim")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        pkg.install(ctx, "neovim")


@register
class JetbrainsToolbox(Module):
    name = "jetbrains-toolbox"
    category = "optional-editors"
    description = "JetBrains Toolbox app."
    gui = True
    profiles = ("optional-editors",)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewCask("jetbrains-toolbox"))

    def _bin(self) -> Path:
        return Path(os.environ["HOME"]) / ".local" / "bin" / "jetbrains-toolbox"

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return self._bin().exists()

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        self._bin().parent.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(
            ["sh", "-c",
             "curl -fsSL 'https://data.services.jetbrains.com/products/download"
             "?code=TBA&platform=linux' -o /tmp/jbtb.tar.gz && "
             f"tar -xzf /tmp/jbtb.tar.gz -C {self._bin().parent} --strip-components=1"]
        )
