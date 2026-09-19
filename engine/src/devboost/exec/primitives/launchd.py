"""launchd primitive — per-user LaunchAgents and system LaunchDaemons (macOS).

The macOS counterpart of ``systemd.py``. Plists are built with stdlib ``plistlib`` and
(re)loaded with the modern ``launchctl bootstrap``/``bootout`` verbs. Every writer is
idempotent: an unchanged plist that is already loaded is left alone.
"""

from __future__ import annotations

import os
import plistlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError
from devboost.model import Ctx

#: System daemons live here (root-owned). Module attribute so tests can redirect it.
DAEMONS_DIR = Path("/Library/LaunchDaemons")


#: A launchd label that is safe to join into a plist path (no `/`, whitespace or leading
#: `-`). Checked before any path is built — the daemon paths are written as root.
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")


def label(name: str) -> str:
    return f"dev.devboost.{name}"


def _checked(lbl: str) -> str:
    if not _LABEL_RE.fullmatch(lbl):
        raise ValueError(f"invalid launchd label {lbl!r}")
    return lbl


def _daemon_plist(lbl: str) -> Path:
    return DAEMONS_DIR / f"{_checked(lbl)}.plist"


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
    keep_alive: bool | Mapping[str, bool] | None = None,
    throttle_interval: int | None = None,
    log_path: Path | None = None,
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
    if keep_alive is not None:
        data["KeepAlive"] = keep_alive if isinstance(keep_alive, bool) else dict(keep_alive)
    if throttle_interval is not None:
        data["ThrottleInterval"] = throttle_interval
    if log_path is not None:
        data["StandardOutPath"] = str(log_path)
        data["StandardErrorPath"] = str(log_path)
    return plistlib.dumps(data)


def agent_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"{_gui_domain()}/{lbl}"]).ok


def agent_current(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
    keep_alive: bool | Mapping[str, bool] | None = None,
    throttle_interval: int | None = None,
    log_path: Path | None = None,
) -> bool:
    """The agent's plist on disk is exactly this one AND launchd has it loaded."""
    path = agent_plist(lbl)
    body = _plist(
        lbl,
        program_args,
        start_interval=start_interval,
        start_calendar=start_calendar,
        run_at_load=run_at_load,
        env=env,
        keep_alive=keep_alive,
        throttle_interval=throttle_interval,
        log_path=log_path,
    )
    return path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl)


def daemon_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"system/{lbl}"]).ok


def agent_plist(lbl: str) -> Path:
    """Where the per-user agent's plist lives."""
    return _agents_dir() / f"{_checked(lbl)}.plist"


def agent_installed(ctx: Ctx, lbl: str) -> bool:
    """The agent's plist is on disk and launchd has it loaded."""
    return agent_plist(lbl).exists() and agent_loaded(ctx, lbl)


def user_agent(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
    keep_alive: bool | Mapping[str, bool] | None = None,
    throttle_interval: int | None = None,
    log_path: Path | None = None,
) -> bool:
    """Install/refresh a per-user LaunchAgent. Returns True when anything changed.

    ``keep_alive`` is launchd's ``KeepAlive`` (``True``, or e.g. ``{"SuccessfulExit":
    False}`` — restart only after a failure, like systemd's ``Restart=on-failure``).
    ``log_path`` receives both stdout and stderr; its directory is created.
    """
    path = agent_plist(lbl)
    body = _plist(
        lbl,
        program_args,
        start_interval=start_interval,
        start_calendar=start_calendar,
        run_at_load=run_at_load,
        env=env,
        keep_alive=keep_alive,
        throttle_interval=throttle_interval,
        log_path=log_path,
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
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
    path = _daemon_plist(lbl)
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
    agent_plist(lbl).unlink(missing_ok=True)


def remove_daemon(ctx: Ctx, lbl: str) -> None:
    """Unload and delete a root LaunchDaemon (a missing one is not an error).

    A failed ``bootout`` is ignored (the job may not be loaded). A failed ``rm -f`` is not:
    ``rm -f`` succeeds on a missing file, so a failure means the root job stays installed
    (no sudo credentials, permission denied) and the caller must not report it removed.
    """
    path = _daemon_plist(lbl)
    ctx.ex.run(["launchctl", "bootout", f"system/{lbl}"], sudo=True)
    res = ctx.ex.run(["rm", "-f", str(path)], sudo=True)
    if not res.ok:
        raise InstallError("launchd", f"rm -f {path}", res.code)
