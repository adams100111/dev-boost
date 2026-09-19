"""browser-mcp on macOS — keep the Playwright MCP launcher running as a LaunchAgent.

On Linux the dotfiles own this (a systemd --user unit that chezmoi enables; see
dotfiles/dot_config/systemd/user/README.md), so there is no engine module there. A dotfile
cannot load a launchd job, hence this macOS-only module (spec §2, plan D9).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from devboost.core.errors import ConfigError
from devboost.core.registry import register
from devboost.exec.primitives import launchd
from devboost.model import Ctx, Module
from devboost.modules._launchd_jobs import launchd_path, log_path
from devboost.modules.shell import Dotfiles

_NAME = "browser-mcp"


def _home() -> Path:
    return Path(os.environ["HOME"])


def _launcher() -> Path:
    return _home() / ".local" / "bin" / "browser-mcp"


def _agent() -> dict[str, Any]:
    """The agent's plist inputs — one source for install and verify (M4-D7)."""
    # npx comes from mise's shims, first on PATH — as in the systemd unit.
    shims = _home() / ".local" / "share" / "mise" / "shims"
    return {
        "lbl": launchd.label(_NAME),
        "program_args": [str(_launcher())],
        "run_at_load": True,
        # Restart after a failure only (≈ Restart=on-failure); once a minute while the
        # tailnet is down rather than launchd's default every 10 s.
        "keep_alive": {"SuccessfulExit": False},
        "throttle_interval": 60,
        "env": {"PATH": f"{shims}:{launchd_path()}"},
        "log_path": log_path(_NAME),
    }


@register
class BrowserMcp(Module):
    name = "browser-mcp"
    category = "remote"
    description = "Playwright MCP on the tailnet for remote Claude Code sessions (launchd agent)."
    families: ClassVar[tuple[str, ...]] = ("macos",)
    # Its own install IS the macOS path (a LaunchAgent); Linux plans drop it (families).
    portable = True
    requires = (Dotfiles,)
    profiles = ("remote",)
    gui = True

    def verify(self, ctx: Ctx) -> bool:
        return _launcher().exists() and launchd.agent_current(ctx, **_agent())

    def install(self, ctx: Ctx) -> None:
        if not _launcher().exists():
            raise ConfigError(f"{_launcher()} is missing — run: devboost install dotfiles")
        launchd.user_agent(ctx, **_agent())
