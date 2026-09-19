from __future__ import annotations

from typing import ClassVar

import pytest

from devboost.core.errors import DependencyCycle, ManifestError, NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.registry import _validate
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module

FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Store(Module):
    name: ClassVar[str] = "t-store"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser("device not approved", "devboost pass approve box")


class _Reader(Module):
    name: ClassVar[str] = "t-reader"
    after = (_Store,)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover — verify passes
        raise AssertionError


def test_after_orders_when_both_selected() -> None:
    mods = {"t-store": _Store, "t-reader": _Reader}
    assert toposort(["t-reader", "t-store"], mods) == ["t-store", "t-reader"]


def test_after_never_pulls_target_into_plan() -> None:
    mods = {"t-store": _Store, "t-reader": _Reader}
    assert toposort(["t-reader"], mods) == ["t-reader"]


def test_blocked_after_target_does_not_block_dependent() -> None:
    mods: dict[str, type[Module]] = {"t-store": _Store, "t-reader": _Reader}
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    res = run_plan([PlannedModule("t-store"), PlannedModule("t-reader")], mods, ctx)
    assert [(r.name, r.status) for r in res] == [
        ("t-store", "blocked"), ("t-reader", "skip"),
    ]


def test_unknown_after_ref_rejected() -> None:
    class _Orphan(Module):
        name: ClassVar[str] = "t-orphan"
        after = (_Store,)

    with pytest.raises(ManifestError, match="after"):
        _validate({"t-orphan": _Orphan})


def test_after_cycle_detected() -> None:
    class _A(Module):
        name: ClassVar[str] = "t-a"

    class _B(Module):
        name: ClassVar[str] = "t-b"
        after = (_A,)

    _A.after = (_B,)
    with pytest.raises(DependencyCycle):
        _validate({"t-a": _A, "t-b": _B})
