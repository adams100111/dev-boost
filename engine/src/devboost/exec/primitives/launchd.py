"""launchd primitive — per-user LaunchAgents and system LaunchDaemons (macOS).

The macOS counterpart of ``systemd.py``. Plists are built with stdlib ``plistlib`` and
(re)loaded with the modern ``launchctl bootstrap``/``bootout`` verbs. Every writer is
idempotent: an unchanged plist that is already loaded is left alone.
"""

from __future__ import annotations

import os
import plistlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError
from devboost.model import Ctx

#: System daemons live here (root-owned). Module attribute so tests can redirect it.
DAEMONS_DIR = Path("/Library/LaunchDaemons")


def label(name: str) -> str:
    return f"dev.devboost.{name}"


def _agents_dir() -> Path:
    return Path(os.environ["HOME"]) / "Library" / "LaunchAgents"


def _gui_domain() -> str:
    return f"gui/{os.getuid()}"


def _plist(
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None,
    start_calendar: Mapping[str, int] | None,
    run_at_load: bool,
    env: Mapping[str, str] | None,
) -> bytes:
    data: dict[str, Any] = {"Label": lbl, "ProgramArguments": list(program_args)}
    if start_interval is not None:
        data["StartInterval"] = start_interval
    if start_calendar is not None:
        data["StartCalendarInterval"] = dict(start_calendar)
    if run_at_load:
        data["RunAtLoad"] = True
    if env:
        data["EnvironmentVariables"] = dict(env)
    return plistlib.dumps(data)


def agent_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"{_gui_domain()}/{lbl}"]).ok


def daemon_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"system/{lbl}"]).ok


def user_agent(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Install/refresh a per-user LaunchAgent. Returns True when anything changed."""
    path = _agents_dir() / f"{lbl}.plist"
    body = _plist(
        lbl,
        program_args,
        start_interval=start_interval,
        start_calendar=start_calendar,
        run_at_load=run_at_load,
        env=env,
    )
    if path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    ctx.ex.run(["launchctl", "bootout", f"{_gui_domain()}/{lbl}"])  # not loaded → ignored
    res = ctx.ex.run(["launchctl", "bootstrap", _gui_domain(), str(path)])
    if not res.ok:
        raise InstallError(
            "launchd", f"launchctl bootstrap {_gui_domain()} {path}", res.code
        )
    return True


def system_daemon(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    run_at_load: bool = True,
    start_interval: int | None = None,
) -> bool:
    """Install/refresh a root LaunchDaemon (root:wheel 644, as launchd requires)."""
    path = DAEMONS_DIR / f"{lbl}.plist"
    body = _plist(
        lbl,
        program_args,
        start_interval=start_interval,
        start_calendar=None,
        run_at_load=run_at_load,
        env=None,
    )
    if path.exists() and path.read_bytes() == body and daemon_loaded(ctx, lbl):
        return False
    ctx.ex.run(["tee", str(path)], sudo=True, stdin=body.decode("utf-8"))
    ctx.ex.run(["chown", "root:wheel", str(path)], sudo=True)
    ctx.ex.run(["chmod", "644", str(path)], sudo=True)
    ctx.ex.run(["launchctl", "bootout", f"system/{lbl}"], sudo=True)
    res = ctx.ex.run(["launchctl", "bootstrap", "system", str(path)], sudo=True)
    if not res.ok:
        raise InstallError("launchd", f"launchctl bootstrap system {path}", res.code)
    return True


def remove_agent(ctx: Ctx, lbl: str) -> None:
    ctx.ex.run(["launchctl", "bootout", f"{_gui_domain()}/{lbl}"])
    (_agents_dir() / f"{lbl}.plist").unlink(missing_ok=True)
