"""The verify-guarded, idempotent install loop over a built plan."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from devboost.core import log
from devboost.core.errors import NeedsUser, PresentUnmanaged
from devboost.core.plan import PlannedModule
from devboost.exec.primitives import tcc
from devboost.model import Ctx, Module

Status = Literal["ok", "skip", "fail", "blocked"]


@dataclass(frozen=True)
class RunResult:
    name: str
    status: Status
    detail: str = ""
    #: Whether a fail/blocked result stops the modules that require this one. False for
    #: a TCC-pending result: the install itself succeeded, only the user's grant is owed.
    blocks_dependents: bool = True


def module_ctx(ctx: Ctx, name: str, forced: Collection[str] | None) -> Ctx:
    """The context one module runs with: ``--force`` applies only to the ``forced`` names.

    ``forced=None`` forces every module (``--update`` force-refreshes its whole filtered
    plan). ``devboost install --force ripgrep`` forces ripgrep, not the dependencies the
    plan added for it (xcode-clt, homebrew): reinstalling those was never asked for.
    """
    if not ctx.force or forced is None or name in forced:
        return ctx
    return replace(ctx, force=False)


def run_plan(
    plan: list[PlannedModule],
    modules: Mapping[str, type[Module]],
    ctx: Ctx,
    *,
    forced: Collection[str] | None = None,
) -> list[RunResult]:
    # Tracks modules that either failed or were blocked; used to propagate cascades.
    failed_or_blocked: set[str] = set()
    results: list[RunResult] = []
    for pm in plan:
        mctx = module_ctx(ctx, pm.name, forced)
        result = _run_one(pm, modules[pm.name](), mctx, failed_or_blocked)
        if result.status in ("fail", "blocked") and result.blocks_dependents:
            failed_or_blocked.add(pm.name)
        results.append(result)
    return results


def _tcc_gate(pm: PlannedModule, mod: Module, ctx: Ctx, ok: RunResult) -> RunResult:
    """On macOS, a module is only done once the user has granted its app's permissions."""
    if ctx.os.family != "macos" or not type(mod).tcc:
        return ok
    missing = tcc.pending(pm.name, type(mod).tcc)
    if not missing:
        return ok
    hint = tcc.fix_hint(missing)
    log.warn(
        f"{pm.name}: needs permissions — {hint}; "
        f"then `devboost permissions --confirm {pm.name}`"
    )
    return RunResult(
        pm.name, "blocked", f"needs-user: grant permissions → {hint}", blocks_dependents=False
    )


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
        return _tcc_gate(pm, mod, ctx, RunResult(pm.name, "skip", "already-installed"))
    try:
        mod.install(ctx)
    except NeedsUser as exc:
        log.warn(f"{pm.name}: needs you — {exc.reason}. Fix: {exc.how_to_fix}")
        return RunResult(pm.name, "blocked", f"needs-user: {exc.reason} → {exc.how_to_fix}")
    except PresentUnmanaged as exc:
        log.skip(f"{pm.name} ({exc.item} already installed outside dev-boost — left untouched)")
        return RunResult(pm.name, "skip", "present-unmanaged")
    except Exception as exc:  # noqa: BLE001 — surface any module failure as a fail result
        log.error(f"{pm.name}: {exc}")
        return RunResult(pm.name, "fail", str(exc))
    if mod.verify(ctx):
        log.ok(f"installed {pm.name}")
        return _tcc_gate(pm, mod, ctx, RunResult(pm.name, "ok"))
    log.error(f"{pm.name}: verify failed after install")
    return RunResult(pm.name, "fail", "verify-failed-after-install")
