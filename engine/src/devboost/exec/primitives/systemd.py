"""systemd primitive — write + enable per-user units (services/timers)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.model import Ctx


def _user_unit_dir() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "systemd" / "user"


def write_user_unit(ctx: Ctx, name: str, content: str) -> None:
    d = _user_unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")


def enable_user_unit(ctx: Ctx, name: str, *, now: bool = False) -> None:
    argv = ["systemctl", "--user", "enable", *(["--now"] if now else []), name]
    ctx.ex.run(argv)


def enable_system_unit(ctx: Ctx, name: str, *, now: bool = False) -> None:
    argv = ["systemctl", "enable", *(["--now"] if now else []), name]
    ctx.ex.run(argv, sudo=True)


def is_enabled(ctx: Ctx, name: str, *, user: bool = False) -> bool:
    scope = ["--user"] if user else []
    return ctx.ex.run(["systemctl", *scope, "is-enabled", name]).ok
