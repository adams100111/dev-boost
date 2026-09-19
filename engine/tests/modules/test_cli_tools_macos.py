from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.cli_tools import (
    Atuin,
    Bash,
    Curl,
    Delta,
    Dust,
    Eza,
    Fastfetch,
    Gh,
    Lazydocker,
    Lazygit,
    Sd,
    Tealdeer,
    Unzip,
    WlClipboard,
    Yq,
)

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")

BREW_BACKED: list[tuple[type[PackageModule], str]] = [
    (Eza, "eza"),
    (Atuin, "atuin"),
    (Lazygit, "lazygit"),
    (Lazydocker, "lazydocker"),
    (Dust, "dust"),
    (Sd, "sd"),
    (Yq, "yq"),
    (Tealdeer, "tealdeer"),
    (Fastfetch, "fastfetch"),
    (Gh, "gh"),
    (Delta, "git-delta"),
    (Bash, "bash"),
]


@pytest.mark.parametrize(("cls", "formula"), BREW_BACKED)
def test_installs_its_formula_on_macos(cls: type[PackageModule], formula: str) -> None:
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", formula]]


@pytest.mark.parametrize(("cls", "formula"), BREW_BACKED)
def test_verifies_through_brew_on_macos(cls: type[PackageModule], formula: str) -> None:
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--formula", "--versions", formula]]


def test_linux_install_paths_are_unchanged() -> None:
    ex = FakeExecutor()
    Lazygit().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "copr", "enable", "-y", "atim/lazygit"] in ex.calls
    ex = FakeExecutor()
    Eza().install(Ctx(os=UBUNTU, ex=ex))
    assert ex.calls[0][:2] == ["sh", "-c"]
    assert Tealdeer().verify(Ctx(os=UBUNTU, ex=FakeExecutor(present={"tealdeer"}))) is True


def test_macos_already_provides_curl_unzip_and_the_clipboard(tmp_path: Path) -> None:
    for cls in (Curl, Unzip, WlClipboard):
        assert "macos" in cls.provided_by, cls.name
    modules = load()
    plan = build_plan(["curl", "unzip", "wl-clipboard"], modules, MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {
        "curl": "provided-by-macos",
        "unzip": "provided-by-macos",
        "wl-clipboard": "provided-by-macos",
    }


def test_bash_is_a_macos_only_tool() -> None:
    assert Bash.families == ("macos",)
    assert Bash.self_updating is True
