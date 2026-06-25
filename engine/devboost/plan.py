from collections.abc import Mapping
from dataclasses import dataclass

from devboost.manifest import Module
from devboost.osinfo import OsInfo


@dataclass(frozen=True)
class PlannedModule:
    name: str
    verify: str
    steps: tuple[str, ...]
    skip_reason: str | None


def resolve_steps(mod: Module, os_info: OsInfo) -> tuple[str, ...]:
    steps: list[str] = []
    for key in (os_info.distro, os_info.family, "default"):
        if key in mod.install:
            steps.append(mod.install[key])
            break
    if "mise" in mod.fallback:
        steps.append(f"mise use -g {mod.fallback['mise']}")
    if "script" in mod.fallback:
        steps.append(f"curl -fsSL {mod.fallback['script']} | sh")
    return tuple(steps)


def build_plan(
    order: list[str],
    modules: Mapping[str, Module],
    os_info: OsInfo,
    headless: bool,
) -> list[PlannedModule]:
    plan: list[PlannedModule] = []
    for name in order:
        mod = modules[name]
        steps = resolve_steps(mod, os_info)
        skip: str | None = None
        if mod.gui and headless:
            skip = "headless-gui"
        elif not steps:
            skip = "unsupported-os"
        plan.append(PlannedModule(mod.name, mod.verify, steps, skip))
    return plan
