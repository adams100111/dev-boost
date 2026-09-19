"""browser-mcp — the Playwright MCP launcher, kept running for remote Claude Code sessions.

Opt-in (C-M4-SEC2): no profile includes it; ``devboost install browser-mcp`` turns it on.
The server it runs has ``browser_run_code_unsafe`` and no auth, so any tailnet peer that can
reach tcp:8931 can run code as you — restrict the port with a Tailscale ACL
(docs/remote-dev.md).

- macOS: a LaunchAgent (``dev.devboost.browser-mcp``) runs the dotfiles launcher.
- Linux: the dotfiles ship the systemd ``--user`` unit, inert; this module is the only
  thing that enables it (the dotfiles no longer carry a ``default.target.wants`` link).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devboost.core import log
from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import launchd, systemd
from devboost.model import Ctx, Module
from devboost.modules._launchd_jobs import launchd_path, log_path
from devboost.modules._playwright_mcp import PLAYWRIGHT_MCP_VERSION
from devboost.modules.shell import Dotfiles

_NAME = "browser-mcp"
_UNIT = "browser-mcp.service"
ACL_WARNING = (
    "browser-mcp: port 8931 runs code as you for any tailnet peer that can reach it — "
    "restrict tcp:8931 on this machine with a Tailscale ACL (docs/remote-dev.md)"
)


def _home() -> Path:
    return Path(os.environ["HOME"])


def _launcher() -> Path:
    return _home() / ".local" / "bin" / "browser-mcp"


def _require_launcher() -> None:
    if not _launcher().exists():
        raise ConfigError(f"{_launcher()} is missing — run: devboost install dotfiles")


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
        # The launcher runs `npx @playwright/mcp@$PLAYWRIGHT_MCP_VERSION` — the one pin.
        # launchd never rotates StandardOutPath, so the launcher truncates BROWSER_MCP_LOG
        # when it has grown past its cap (a restart loop appends every minute).
        "env": {
            "PATH": f"{shims}:{launchd_path()}",
            "PLAYWRIGHT_MCP_VERSION": PLAYWRIGHT_MCP_VERSION,
            "BROWSER_MCP_LOG": str(log_path(_NAME)),
        },
        "log_path": log_path(_NAME),
    }


@dataclass(frozen=True)
class _MacBrowserMcp:
    """macOS: a dotfile cannot load a launchd job, so the module writes the agent."""

    def verify(self, ctx: Ctx) -> bool:
        return _launcher().exists() and launchd.agent_current(ctx, **_agent())

    def install(self, ctx: Ctx) -> None:
        _require_launcher()
        log.warn(ACL_WARNING)
        launchd.user_agent(ctx, **_agent())


@register
class BrowserMcp(Module):
    name = "browser-mcp"
    category = "remote"
    description = (
        "Opt-in: Playwright MCP on the tailnet for remote Claude Code sessions "
        "(systemd unit / launchd agent)."
    )
    requires = (Dotfiles,)
    # No profile (C-M4-SEC2): opt-in by name only, like agent-sudo.
    profiles = ()
    gui = True
    per_os = OsMap(macos=_MacBrowserMcp())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        unit = systemd._user_unit_dir() / _UNIT
        return (
            _launcher().exists()
            and unit.is_file()
            and systemd.is_enabled(ctx, _UNIT, user=True)
        )

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        _require_launcher()
        if not (systemd._user_unit_dir() / _UNIT).is_file():
            raise ConfigError(
                f"{systemd._user_unit_dir() / _UNIT} is missing — run: devboost install dotfiles"
            )
        log.warn(ACL_WARNING)
        ctx.ex.run(["systemctl", "--user", "daemon-reload"])
        systemd.enable_user_unit(ctx, _UNIT, now=True)
