"""tpm — clone the tmux plugin manager (idempotent)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.registry import register
from devboost.model import Ctx, Module


def _tpm_dir() -> Path:
    return Path(os.environ["HOME"]) / ".tmux" / "plugins" / "tpm"


@register
class Tpm(Module):
    name = "tpm"
    category = "cli"
    description = "tmux plugin manager."
    profiles = ("cli",)

    def verify(self, ctx: Ctx) -> bool:
        return _tpm_dir().is_dir()

    def install(self, ctx: Ctx) -> None:
        d = _tpm_dir()
        if d.is_dir():
            return
        d.parent.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(["git", "clone", "https://github.com/tmux-plugins/tpm", str(d)])
