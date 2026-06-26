"""dev-hygiene profile — the aspire-gc user timer."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import systemd
from devboost.model import Ctx, Module
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
    description = "Hourly GC of orphaned Aspire/dev containers (systemd --user timer)."
    requires = (Docker,)
    profiles = ("dev-hygiene",)

    def verify(self, ctx: Ctx) -> bool:
        return systemd._user_unit_dir().joinpath("aspire-gc.timer").exists()

    def install(self, ctx: Ctx) -> None:
        systemd.write_user_unit(ctx, "aspire-gc.service", _SERVICE)
        systemd.write_user_unit(ctx, "aspire-gc.timer", _TIMER)
        systemd.enable_user_unit(ctx, "aspire-gc.timer", now=True)
