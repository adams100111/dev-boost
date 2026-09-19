"""dev-hygiene profile — the aspire-gc user timer."""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import systemd
from devboost.model import Ctx, Module
from devboost.modules._launchd_jobs import LaunchdTimer
from devboost.modules.docker import Docker

_SERVICE = (
    "[Unit]\nDescription=devboost Aspire/dev-container GC (devboost dev gc)\n\n"
    "[Service]\nType=oneshot\nExecStart=/bin/sh -c 'devboost dev gc'\n"
)
_TIMER = (
    "[Unit]\nDescription=hourly devboost dev gc\n\n[Timer]\nOnCalendar=hourly\nPersistent=true\n\n"
    "[Install]\nWantedBy=timers.target\n"
)


@register
class AspireGc(Module):
    name = "aspire-gc"
    category = "dev-hygiene"
    description = "Hourly GC of orphaned Aspire/dev containers (systemd timer / launchd agent)."
    requires = (Docker,)
    profiles = ("dev-hygiene",)
    per_os = OsMap(macos=LaunchdTimer("aspire-gc", "devboost dev gc", "hourly"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return systemd._user_unit_dir().joinpath("aspire-gc.timer").exists()

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        systemd.write_user_unit(ctx, "aspire-gc.service", _SERVICE)
        systemd.write_user_unit(ctx, "aspire-gc.timer", _TIMER)
        systemd.enable_user_unit(ctx, "aspire-gc.timer", now=True)
