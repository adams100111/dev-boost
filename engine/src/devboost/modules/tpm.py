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


_PERSIST_PLUGINS = {
    "tmux-resurrect": "https://github.com/tmux-plugins/tmux-resurrect",
    "tmux-continuum": "https://github.com/tmux-plugins/tmux-continuum",
}


def _plugin_dir(name: str) -> Path:
    return Path(os.environ["HOME"]) / ".tmux" / "plugins" / name


@register
class TmuxPersist(Module):
    name = "tmux-persist"
    category = "cli"
    description = "tmux-resurrect + tmux-continuum — restore tmux sessions across a reboot."
    profiles = ("cli",)

    def verify(self, ctx: Ctx) -> bool:
        return all(_plugin_dir(n).is_dir() for n in _PERSIST_PLUGINS)

    def install(self, ctx: Ctx) -> None:
        # Cloned directly (not via TPM's prefix+I) — the tmux config run-shells them.
        for name, url in _PERSIST_PLUGINS.items():
            d = _plugin_dir(name)
            if d.is_dir():
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            ctx.ex.run(["git", "clone", url, str(d)])
