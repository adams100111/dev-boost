"""Build the per-module decision plan (skip reasons) before execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from devboost.core.osinfo import OsInfo
from devboost.model import Module


@dataclass(frozen=True)
class PlannedModule:
    name: str
    skip_reason: str | None = None


def build_plan(
    order: list[str],
    modules: Mapping[str, type[Module]],
    os_info: OsInfo,
) -> list[PlannedModule]:
    plan: list[PlannedModule] = []
    for name in order:
        cls = modules[name]
        reason: str | None = None
        if cls.gui and os_info.headless:
            reason = "headless-gui"
        elif not _supported(cls, os_info):
            reason = "unsupported-os"
        plan.append(PlannedModule(name=name, skip_reason=reason))
    return plan


def _supported(cls: type[Module], os_info: OsInfo) -> bool:
    """A per-OS module is unsupported when its per_os map has no entry for this OS."""
    if not cls.per_os.fedora and not cls.per_os.debian and not cls.per_os.arch \
            and not cls.per_os.default:
        return True  # uniform module — supported everywhere it can run
    return cls.per_os.get(os_info) is not None
