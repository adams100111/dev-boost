from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import tcc
from devboost.model import Ctx, Module, TccGrant

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _NeedsA11y(Module):
    name: ClassVar[str] = "needs-a11y"
    tcc: ClassVar[tuple[TccGrant, ...]] = (TccGrant("Accessibility", "Tiler"),)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover
        pass


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def _status(os: OsInfo) -> tuple[str, str]:
    r = run_plan([PlannedModule("needs-a11y")], {"needs-a11y": _NeedsA11y},
                 Ctx(os=os, ex=FakeExecutor()))[0]
    return r.status, r.detail


def test_unconfirmed_grant_blocks_on_macos() -> None:
    status, detail = _status(MAC)
    assert status == "blocked"
    assert "Privacy_Accessibility" in detail


def test_confirmed_grant_passes() -> None:
    tcc.confirm("needs-a11y", _NeedsA11y.tcc)
    assert _status(MAC) == ("skip", "already-installed")


def test_tcc_ignored_off_macos() -> None:
    assert _status(FEDORA) == ("skip", "already-installed")
