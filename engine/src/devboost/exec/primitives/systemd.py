"""systemd primitive — write + enable per-user units (services/timers)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.model import Ctx


def _user_unit_dir() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "systemd" / "user"


def unit_current(name: str, content: str) -> bool:
    """The user unit on disk is exactly *content*."""
    p = _user_unit_dir() / name
    return p.exists() and p.read_text(encoding="utf-8") == content


def write_user_unit(ctx: Ctx, name: str, content: str) -> bool:
    """Write a user unit; True when it changed. A change is followed by `daemon-reload`, so
    systemd uses the new unit without a re-login (identical content: nothing runs)."""
    if unit_current(name, content):
        return False
    d = _user_unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    ctx.ex.run(["systemctl", "--user", "daemon-reload"])
    return True


def enable_user_unit(ctx: Ctx, name: str, *, now: bool = False) -> None:
    argv = ["systemctl", "--user", "enable", *(["--now"] if now else []), name]
    ctx.ex.run(argv)


def enable_system_unit(ctx: Ctx, name: str, *, now: bool = False) -> None:
    argv = ["systemctl", "enable", *(["--now"] if now else []), name]
    ctx.ex.run(argv, sudo=True)


def is_enabled(ctx: Ctx, name: str, *, user: bool = False) -> bool:
    scope = ["--user"] if user else []
    return ctx.ex.run(["systemctl", *scope, "is-enabled", name]).ok


def is_active(ctx: Ctx, name: str, *, user: bool = False) -> bool:
    scope = ["--user"] if user else []
    return ctx.ex.run(["systemctl", *scope, "is-active", name]).ok
