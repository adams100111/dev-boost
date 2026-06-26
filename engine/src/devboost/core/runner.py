"""The verify-guarded, idempotent install loop over a built plan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from devboost.core import log
from devboost.core.plan import PlannedModule
from devboost.model import Ctx, Module

Status = Literal["ok", "skip", "fail"]


@dataclass(frozen=True)
class RunResult:
    name: str
    status: Status
    detail: str = ""


def run_plan(
    plan: list[PlannedModule],
    modules: Mapping[str, type[Module]],
    ctx: Ctx,
) -> list[RunResult]:
    results: list[RunResult] = []
    for pm in plan:
        results.append(_run_one(pm, modules[pm.name](), ctx))
    return results


def _run_one(pm: PlannedModule, mod: Module, ctx: Ctx) -> RunResult:
    if pm.skip_reason is not None:
        log.skip(f"{pm.name} ({pm.skip_reason})")
        return RunResult(pm.name, "skip", pm.skip_reason)
    if ctx.dry_run:
        log.info(f"would install {pm.name}")
        return RunResult(pm.name, "ok", "dry-run")
    if not ctx.force and mod.verify(ctx):
        log.skip(f"{pm.name} (already installed)")
        return RunResult(pm.name, "skip", "already-installed")
    try:
        mod.install(ctx)
    except Exception as exc:  # noqa: BLE001 — surface any module failure as a fail result
        log.error(f"{pm.name}: {exc}")
        return RunResult(pm.name, "fail", str(exc))
    if mod.verify(ctx):
        log.ok(f"installed {pm.name}")
        return RunResult(pm.name, "ok")
    log.error(f"{pm.name}: verify failed after install")
    return RunResult(pm.name, "fail", "verify-failed-after-install")
