"""The verify-guarded, idempotent install loop over a built plan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from devboost.core import log
from devboost.core.plan import PlannedModule
from devboost.model import Ctx, Module

Status = Literal["ok", "skip", "fail", "blocked"]


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
    # Tracks modules that either failed or were blocked; used to propagate cascades.
    failed_or_blocked: set[str] = set()
    results: list[RunResult] = []
    for pm in plan:
        result = _run_one(pm, modules[pm.name](), ctx, failed_or_blocked)
        if result.status in ("fail", "blocked"):
            failed_or_blocked.add(pm.name)
        results.append(result)
    return results


def _run_one(pm: PlannedModule, mod: Module, ctx: Ctx, failed: set[str]) -> RunResult:
    if pm.skip_reason is not None:
        log.skip(f"{pm.name} ({pm.skip_reason})")
        return RunResult(pm.name, "skip", pm.skip_reason)
    # Dependency-aware abort: since the plan is in topological order, checking direct
    # requires against *failed* (which includes previously-blocked modules) is sufficient
    # to propagate cascade failures transitively.
    for dep_cls in type(mod).requires:
        if dep_cls.name in failed:
            log.warn(f"{pm.name}: blocked — required module {dep_cls.name!r} did not succeed")
            return RunResult(pm.name, "blocked", f"required-failed:{dep_cls.name}")
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
