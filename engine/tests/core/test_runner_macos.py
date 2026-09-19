from __future__ import annotations

from typing import ClassVar

from devboost.core.errors import NeedsUser, PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.macos import Rosetta
from tests.scripted import Scripted

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


class _Present(Module):
    """Installed; records the force flag each install() saw."""

    name: ClassVar[str] = "present-dep"
    seen: ClassVar[list[bool]] = []

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:
        type(self).seen.append(ctx.force)


class _PresentSelected(_Present):
    name: ClassVar[str] = "present-selected"
    requires = (_Present,)


def test_force_reaches_only_the_forced_modules() -> None:
    # `install --force present-selected` reinstalls it, not the dependency the plan added.
    _Present.seen.clear()
    modules = {"present-dep": _Present, "present-selected": _PresentSelected}
    plan = [PlannedModule("present-dep"), PlannedModule("present-selected")]
    ctx = Ctx(os=MAC, ex=FakeExecutor(), force=True)
    results = run_plan(plan, modules, ctx, forced={"present-selected"})
    assert [(r.name, r.status, r.detail) for r in results] == [
        ("present-dep", "skip", "already-installed"),
        ("present-selected", "ok", ""),
    ]
    assert _Present.seen == [True]  # only the selected module's install ran, forced


def test_forced_none_forces_every_module() -> None:
    # --update force-refreshes its whole filtered plan.
    _Present.seen.clear()
    modules = {"present-dep": _Present, "present-selected": _PresentSelected}
    plan = [PlannedModule("present-dep"), PlannedModule("present-selected")]
    run_plan(plan, modules, Ctx(os=MAC, ex=FakeExecutor(), force=True))
    assert _Present.seen == [True, True]


# --- AF1: a session without sudo blocks pending sudo modules --------------------------


def test_no_sudo_session_blocks_pending_sudo_module_with_the_fix() -> None:
    mac = OsInfo("macos", "macos", "aarch64", version_id="27.0")
    ex = Scripted(answers={("arch", "-x86_64"): Result(1)})  # Rosetta missing
    [res] = run_plan([PlannedModule("rosetta")], {"rosetta": Rosetta}, Ctx(mac, ex, no_sudo=True))
    assert res.status == "blocked"
    assert res.detail.endswith(
        "run `devboost install rosetta` in a terminal (needs your password)"
    )
    assert not any("softwareupdate" in c for c in ex.calls)


def test_no_sudo_session_leaves_present_or_unflagged_modules_alone() -> None:
    mac = OsInfo("macos", "macos", "aarch64", version_id="27.0")
    [res] = run_plan(
        [PlannedModule("rosetta")], {"rosetta": Rosetta}, Ctx(mac, Scripted(), no_sudo=True)
    )
    assert res.status == "skip"  # Rosetta present: nothing pending
    [res2] = run_plan(
        [PlannedModule("needs-user-mod")],
        {"needs-user-mod": _NeedsUserMod},
        Ctx(MAC, FakeExecutor(), no_sudo=True),
    )
    assert res2.status == "blocked" and "Apple ID" in res2.detail  # its own reason, not sudo
