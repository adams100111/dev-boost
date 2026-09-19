"""Move this Mac to another Docker runtime — `devboost docker use` (spec §4, plan D17)."""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core import log
from devboost.core.errors import DevbootError, InstallError
from devboost.core.registry import load
from devboost.core.settings import Settings
from devboost.core.userconfig import DockerRuntimeName, selected_docker_runtime, set_user_value
from devboost.model import Ctx
from devboost.modules._docker_runtime import license_note, runtime_for, use_context
from devboost.modules.docker import BUILDER_GC

#: Re-verified after a switch (spec §4 step 5). The first two are what the switch itself
#: sets up; the others may legitimately not be installed on this Mac.
REVERIFY: tuple[str, ...] = ("docker", "docker-build-gc", "aspire-gc", "ddev", "data-services")
REQUIRED: frozenset[str] = frozenset({"docker", "docker-build-gc"})


@dataclass(frozen=True)
class SwitchReport:
    previous: DockerRuntimeName
    target: DockerRuntimeName
    checks: tuple[tuple[str, bool], ...]

    @property
    def ok(self) -> bool:
        return all(passed for name, passed in self.checks if name in REQUIRED)


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
            raise InstallError("ddev", "ddev snapshot --all", res.code)
    if not ctx.ex.run(["ddev", "poweroff"]).ok:
        # Not fatal: stopping the old runtime below stops ddev's containers with it.
        log.warn("ddev: `ddev poweroff` failed; its containers stop with the old runtime")


def switch_runtime(ctx: Ctx, target: DockerRuntimeName, *, snapshot: bool) -> SwitchReport:
    """Stop the current runtime, bring up ``target``, save the choice, re-verify.

    The old runtime is stopped, never uninstalled: its VM, images and volumes stay on
    disk. Choosing the current runtime again re-runs every configure step (a repair). A
    failure before the last step leaves config.toml naming the previous runtime.
    """
    previous = selected_docker_runtime()
    _snapshot_and_poweroff(ctx, snapshot=snapshot)
    old = runtime_for(previous)
    if previous != target and old.installed(ctx):  # step 3 — stopped, not uninstalled
        old.stop(ctx)
        old.disable_autostart(ctx)
        old.release_socket(ctx)
    new = runtime_for(target)  # step 4
    note = license_note(target)
    if note:
        log.warn(f"docker: {target} — {note}")
    new.install(ctx)
    new.configure(ctx)
    new.start(ctx)
    use_context(ctx, new.context_name)
    if new.merge_daemon_config(ctx, BUILDER_GC):
        new.restart_engine(ctx)
    set_user_value("docker_runtime", target)  # step 5
    env = Settings().docker_runtime
    if env and env != target:
        log.warn(
            f"DEVBOOST_DOCKER_RUNTIME={env} is set and overrides the saved choice — "
            f"unset it to use {target}"
        )
    return SwitchReport(previous, target, tuple((n, _verify(ctx, n)) for n in REVERIFY))
