"""Scheduled jobs on macOS — the launchd twin of dev-boost's systemd --user timers.

systemd ``OnCalendar=hourly|daily`` + ``Persistent=true`` maps to launchd
``StartCalendarInterval``: launchd runs a job whose time passed while the Mac slept once on
wake. A run missed while the Mac was powered off is not caught up — the one difference
(plan D5). Every job is ``/bin/sh -c <script>`` with an explicit PATH, since launchd starts
agents with a bare one, and logs to ``~/Library/Logs/devboost/<name>.log``. Agents are
per-user only: their plists live under ``~/Library/LaunchAgents`` (``launchd.agent_plist``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from devboost.exec.primitives import launchd, pkg
from devboost.model import Ctx

Schedule = Literal["hourly", "daily"]
#: The same wall-clock times as systemd's `hourly` (:00) and `daily` (00:00).
CALENDAR: dict[Schedule, dict[str, int]] = {
    "hourly": {"Minute": 0},
    "daily": {"Hour": 0, "Minute": 0},
}


def _home() -> Path:
    return Path(os.environ["HOME"])


def launchd_path() -> str:
    """PATH for agents: devboost's own bin, Homebrew, then the system dirs."""
    return ":".join([
        str(_home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ])


def log_path(name: str) -> Path:
    return _home() / "Library" / "Logs" / "devboost" / f"{name}.log"


def _job(name: str, script: str, schedule: Schedule) -> dict[str, Any]:
    """The agent's plist inputs — one source for install and verify (M4-D7)."""
    return {
        "lbl": launchd.label(name),
        "program_args": ["/bin/sh", "-c", script],
        "start_calendar": CALENDAR[schedule],
        "env": {"PATH": launchd_path()},
        "log_path": log_path(name),
    }


def schedule_job(ctx: Ctx, name: str, script: str, schedule: Schedule) -> bool:
    """Install/refresh the ``dev.devboost.<name>`` agent. True when anything changed."""
    return launchd.user_agent(ctx, **_job(name, script, schedule))


def job_scheduled(ctx: Ctx, name: str, script: str, schedule: Schedule) -> bool:
    """The agent is exactly this job (same plist bytes) and launchd has it loaded."""
    return launchd.agent_current(ctx, **_job(name, script, schedule))


@dataclass(frozen=True)
class LaunchdTimer:
    """A ``per_os.macos`` strategy: brew ``formulae`` if missing, then schedule ``script``."""

    name: str
    script: str
    schedule: Schedule
    formulae: tuple[str, ...] = ()

    @property
    def uses_brew(self) -> bool:
        """Read by the Homebrew-edge contract (C-R19): only a timer with formulae brews."""
        return bool(self.formulae)

    def verify(self, ctx: Ctx) -> bool:
        return all(pkg.installed(ctx, f) for f in self.formulae) and job_scheduled(
            ctx, self.name, self.script, self.schedule
        )

    def install(self, ctx: Ctx) -> None:
        missing = [f for f in self.formulae if not pkg.installed(ctx, f)]
        if missing:
            pkg.install(ctx, *missing)
        schedule_job(ctx, self.name, self.script, self.schedule)
