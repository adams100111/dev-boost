"""Move this Mac to another Docker runtime — `devboost docker use` (spec §4, plan D17)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from devboost.core import log
from devboost.core.errors import DevbootError, InstallError, PresentUnmanaged
from devboost.core.registry import load
from devboost.core.userconfig import (
    DEFAULT_DOCKER_RUNTIME,
    DOCKER_RUNTIMES,
    DockerRuntimeName,
    load_user_config,
    set_user_value,
)
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import _docker_colima, _docker_desktop
from devboost.modules._docker_runtime import DockerRuntime, license_note, runtime_for
from devboost.modules.docker import BUILDER_GC, _point_cli_at

#: Re-verified after a switch (spec §4 step 5). The first two are what the switch itself
#: sets up; the others may legitimately not be installed on this Mac.
REVERIFY: tuple[str, ...] = ("docker", "docker-build-gc", "aspire-gc", "ddev", "data-services")
REQUIRED: frozenset[str] = frozenset({"docker", "docker-build-gc"})


class SnapshotFailed(InstallError):
    """``ddev snapshot --all`` failed — raised before anything else was touched."""

    def __init__(self, code: int) -> None:
        super().__init__("ddev", "ddev snapshot --all", code)


@dataclass(frozen=True)
class SwitchReport:
    previous: DockerRuntimeName
    target: DockerRuntimeName
    checks: tuple[tuple[str, bool], ...]

    @property
    def ok(self) -> bool:
        return all(passed for name, passed in self.checks if name in REQUIRED)


def saved_runtime() -> DockerRuntimeName:
    """The runtime this Mac was last switched to: config.toml, never the env override.

    ``DEVBOOST_DOCKER_RUNTIME`` names what devboost should drive, not what is running, so
    reading it here would skip stopping the runtime that actually holds the socket.
    """
    return load_user_config().docker_runtime or DEFAULT_DOCKER_RUNTIME


def to_stop(ctx: Ctx, target: DockerRuntimeName) -> list[DockerRuntime]:
    """Every installed runtime except ``target``, the saved one first (step 3).

    Not only the saved one: after a switch that failed half-way, the half-started target
    still runs with autostart on, and going back must stop it too.
    """
    previous = saved_runtime()
    order = [previous, *(n for n in DOCKER_RUNTIMES if n != previous)]
    runtimes = [runtime_for(n) for n in order if n != target]
    return [rt for rt in runtimes if rt.installed(ctx)]


def _colima_release_needs_root(ctx: Ctx) -> bool:
    """Read-only mirror of ``Colima.release_socket``: would it run anything as root?"""
    plist = launchd.DAEMONS_DIR / f"{_docker_colima.SOCKET_LABEL}.plist"
    if plist.exists() or launchd.daemon_loaded(ctx, _docker_colima.SOCKET_LABEL):
        return True
    sock = _docker_colima.DOCKER_SOCK
    return sock.is_symlink() and Path(os.readlink(sock)) == _docker_colima.Colima().socket_path()


def sudo_needed(ctx: Ctx, target: DockerRuntimeName) -> bool:
    """Read-only, and never under-reports (M4-D6, M4-D5a).

    Colima as the saved or target runtime always asks (its socket LaunchDaemon). A Colima
    stopped only as a stray runtime asks when releasing its socket needs root. Docker
    Desktop asks when its cask would link CLIs into root-owned /usr/local.
    """
    if "colima" in (saved_runtime(), target):
        return True
    if target == "docker-desktop" and _docker_desktop.links_need_root(ctx):
        return True
    stray = any(rt.name == "colima" for rt in to_stop(ctx, target))
    return stray and _colima_release_needs_root(ctx)


def _verify(ctx: Ctx, name: str) -> bool:
    cls = load().get(name)
    if cls is None:
        return False
    try:
        return cls().verify(ctx)
    except (DevbootError, OSError):
        return False


def _snapshot_and_poweroff(ctx: Ctx, *, snapshot: bool) -> None:
    """Steps 1–2: ddev databases live in the old runtime's VM — snapshot, then stop.

    A failed snapshot raises before anything else is touched. The snapshots land in each
    project's ``.ddev/db_snapshots`` on the host, so they survive the switch.
    """
    if not ctx.ex.which("ddev"):
        return
    if snapshot:
        res = ctx.ex.run(["ddev", "snapshot", "--all"])
        if not res.ok:
            raise SnapshotFailed(res.code)
    if not ctx.ex.run(["ddev", "poweroff"]).ok:
        # Not fatal: stopping the old runtime below stops ddev's containers with it.
        log.warn("ddev: `ddev poweroff` failed; its containers stop with the old runtime")


def switch_runtime(ctx: Ctx, target: DockerRuntimeName, *, snapshot: bool) -> SwitchReport:
    """Stop the other runtimes, bring up ``target``, save the choice, re-verify.

    Old runtimes are stopped, never uninstalled: their VMs, images and volumes stay on
    disk. Choosing the saved runtime again re-runs every configure step (a repair) and
    stops any other runtime a failed switch left running. A failure before the last step
    leaves config.toml naming the previous runtime.
    """
    previous = saved_runtime()
    _snapshot_and_poweroff(ctx, snapshot=snapshot)
    for old in to_stop(ctx, target):  # step 3 — stopped, not uninstalled
        old.stop(ctx)
        old.disable_autostart(ctx)
        old.release_socket(ctx)
    new = runtime_for(target)  # step 4
    note = license_note(target)
    if note:
        log.warn(f"docker: {target} — {note}")
    try:
        new.install(ctx)
    except PresentUnmanaged as exc:
        # Installed by hand (the vendor's download): present is all the switch needs.
        log.skip(f"docker: {exc.item} already installed outside dev-boost — left untouched")
    new.configure(ctx)
    new.start(ctx)
    _point_cli_at(ctx, new)
    if new.merge_daemon_config(ctx, BUILDER_GC):
        new.restart_engine(ctx)
    set_user_value("docker_runtime", target)  # step 5
    return SwitchReport(previous, target, tuple((n, _verify(ctx, n)) for n in REVERIFY))
