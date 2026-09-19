"""optional-editors profile (opt-in, off the production path)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules.macos import Homebrew


@register
class Neovim(Module):
    name = "neovim"
    category = "optional-editors"
    description = "Neovim editor."
    profiles = ("optional-editors",)
    # install() calls pkg.install unconditionally, which is brew on macOS; not yet
    # macOS-designed (KNOWN_GAPS), but the ordering invariant still holds if it ever runs.
    requires = (Homebrew,)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("nvim")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "neovim")


@register
class JetbrainsToolbox(Module):
    name = "jetbrains-toolbox"
    category = "optional-editors"
    description = "JetBrains Toolbox app."
    gui = True
    profiles = ("optional-editors",)

    def _bin(self) -> Path:
        return Path(os.environ["HOME"]) / ".local" / "bin" / "jetbrains-toolbox"

    def verify(self, ctx: Ctx) -> bool:
        return self._bin().exists()

    def install(self, ctx: Ctx) -> None:
        self._bin().parent.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(
            ["sh", "-c",
             "curl -fsSL 'https://data.services.jetbrains.com/products/download"
             "?code=TBA&platform=linux' -o /tmp/jbtb.tar.gz && "
             f"tar -xzf /tmp/jbtb.tar.gz -C {self._bin().parent} --strip-components=1"]
        )
