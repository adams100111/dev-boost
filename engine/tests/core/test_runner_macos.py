from __future__ import annotations

from typing import ClassVar

from devboost.core.errors import NeedsUser, PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module

MAC = OsInfo("macos", "macos", "aarch64")


class _NeedsUserMod(Module):
    name: ClassVar[str] = "needs-user-mod"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser("Apple ID required", "export XCODES_USERNAME=… and re-run")


class _UnmanagedMod(Module):
    name: ClassVar[str] = "unmanaged-mod"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise PresentUnmanaged("visual-studio-code")


class _Dependent(Module):
    name: ClassVar[str] = "dependent-mod"
    requires = (_NeedsUserMod,)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover — never reached
        raise AssertionError


def _run(*mods: type[Module]) -> dict[str, tuple[str, str]]:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    plan = [PlannedModule(m.name) for m in mods]
    res = run_plan(plan, {m.name: m for m in mods}, ctx)
    return {r.name: (r.status, r.detail) for r in res}


def test_needs_user_is_blocked_with_fix_hint() -> None:
    out = _run(_NeedsUserMod)
    assert out["needs-user-mod"] == (
        "blocked", "needs-user: Apple ID required → export XCODES_USERNAME=… and re-run"
    )


def test_needs_user_blocks_dependents() -> None:
    out = _run(_NeedsUserMod, _Dependent)
    assert out["dependent-mod"][0] == "blocked"


def test_present_unmanaged_is_a_skip_not_a_failure() -> None:
    assert _run(_UnmanagedMod)["unmanaged-mod"] == ("skip", "present-unmanaged")
