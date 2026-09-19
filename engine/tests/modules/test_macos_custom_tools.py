from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.base import Chezmoi
from devboost.modules.editors import Fresh
from devboost.modules.mise import Mise
from devboost.modules.ripgrep import Ripgrep
from devboost.modules.shell import Starship

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

CASES: list[tuple[type[Module], str]] = [
    (Ripgrep, "ripgrep"),
    (Chezmoi, "chezmoi"),
    (Starship, "starship"),
    (Mise, "mise"),
    (Fresh, "fresh-editor"),
]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_installs_the_formula_on_macos(cls: type[Module], formula: str) -> None:
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", formula]]


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_verifies_through_brew_on_macos(cls: type[Module], formula: str) -> None:
    on_path = {"rg", "chezmoi", "starship", "mise", "fresh"}
    ex = FakeExecutor(scripts={"brew": Result(1)}, present=on_path)
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False  # on PATH is not enough on a Mac
    assert ex.calls == [["brew", "list", "--formula", "--versions", formula]]


def test_fresh_seeds_its_config_on_macos(tmp_path: Path) -> None:
    Fresh().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert (tmp_path / ".config" / "fresh" / "config.json").is_file()


def test_linux_keeps_its_installers_and_stays_supported(tmp_path: Path) -> None:
    ex = FakeExecutor()
    Chezmoi().install(Ctx(os=FEDORA, ex=ex))
    assert any("get.chezmoi.io" in " ".join(c) for c in ex.calls)
    names = [cls.name for cls, _ in CASES]
    plan = build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "none")
    assert all(p.skip_reason is None for p in plan), plan
