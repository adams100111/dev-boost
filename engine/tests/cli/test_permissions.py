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


class _AfterA11y(Module):
    """Depends on a TCC-gated module; its install must not wait for the user's grant."""

    name: ClassVar[str] = "after-a11y"
    requires = (_NeedsA11y,)
    installed: ClassVar[bool] = False

    def verify(self, ctx: Ctx) -> bool:
        return type(self).installed

    def install(self, ctx: Ctx) -> None:
        type(self).installed = True


def test_tcc_pending_does_not_block_dependents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_AfterA11y, "installed", False)
    mods: dict[str, type[Module]] = {"needs-a11y": _NeedsA11y, "after-a11y": _AfterA11y}
    res = run_plan(
        [PlannedModule("needs-a11y"), PlannedModule("after-a11y")], mods,
        Ctx(os=MAC, ex=FakeExecutor()),
    )
    out = {r.name: (r.status, r.detail) for r in res}
    # The gated module itself still reports blocked (the user owes it a grant) …
    assert out["needs-a11y"][0] == "blocked"
    # … but installing is done, so its dependent runs instead of `required-failed`.
    assert out["after-a11y"] == ("ok", "")


class _NeedsTwo(Module):
    """Two grants, as voxtype has three — the case the old blanket prompt got wrong."""

    name: ClassVar[str] = "needs-two"
    tcc: ClassVar[tuple[TccGrant, ...]] = (
        TccGrant("Microphone", "Tiler"),
        TccGrant("ListenEvent", "Tiler"),
    )

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover
        pass


def test_each_grant_is_confirmed_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old prompt asked once per MODULE — "Granted everything for voxtype?" — so a
    single yes marked Microphone, Input Monitoring and Accessibility done forever, even
    the ones the user had not switched on. That is how a machine ended up reporting
    "all granted" with its microphone off."""
    from devboost.cli import permissions as perms

    monkeypatch.setattr(perms.osinfo, "detect", lambda: MAC)
    monkeypatch.setattr(perms, "load", lambda: {"needs-two": _NeedsTwo})
    monkeypatch.setattr(perms, "RealExecutor", FakeExecutor)
    monkeypatch.setattr(perms.sys.stdin, "isatty", lambda: True)

    answers = iter([True, False])  # yes to Microphone, no to Input Monitoring
    monkeypatch.setattr(perms.typer, "confirm", lambda *a, **k: next(answers))

    perms.permissions()

    still = {g.service for g in tcc.pending("needs-two", _NeedsTwo.tcc)}
    assert still == {"ListenEvent"}, "a 'no' must not be recorded as granted"


def test_a_prompt_names_the_exact_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    from devboost.cli import permissions as perms

    monkeypatch.setattr(perms.osinfo, "detect", lambda: MAC)
    monkeypatch.setattr(perms, "load", lambda: {"needs-two": _NeedsTwo})
    monkeypatch.setattr(perms, "RealExecutor", FakeExecutor)
    monkeypatch.setattr(perms.sys.stdin, "isatty", lambda: True)

    asked: list[str] = []

    def _confirm(text: str, **k: object) -> bool:
        asked.append(text)
        return False

    monkeypatch.setattr(perms.typer, "confirm", _confirm)
    perms.permissions()

    assert any("Microphone" in q and "Tiler" in q for q in asked)
    assert any("Input Monitoring" in q and "Tiler" in q for q in asked)
