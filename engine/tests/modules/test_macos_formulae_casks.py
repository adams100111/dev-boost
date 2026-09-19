"""Plain Homebrew formulae and casks for the catalog (spec §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules.apps import Bitwarden, Bruno, FlatpakApp, Localsend, Obsidian, Vlc
from devboost.modules.base import BuildTools
from devboost.modules.dev_stacks import Uv
from devboost.modules.editors import Vscode
from devboost.modules.macos import XcodeClt
from devboost.modules.mosh import Mosh
from devboost.modules.multimedia import FfmpegFull
from devboost.modules.optional import JetbrainsToolbox, Neovim
from devboost.modules.system import Smartmontools

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

CASK_APPS: list[tuple[type[FlatpakApp], str]] = [
    (Obsidian, "obsidian"), (Bruno, "bruno"), (Bitwarden, "bitwarden"),
    (Localsend, "localsend"), (Vlc, "vlc"),
]
STRATEGIES: list[tuple[type[Module], Installer]] = [
    (Vscode, BrewCask("visual-studio-code")),
    (JetbrainsToolbox, BrewCask("jetbrains-toolbox")),
    (Neovim, BrewFormula("neovim")),
    (Mosh, BrewFormula("mosh")),
    (Uv, BrewFormula("uv")),
    (Smartmontools, BrewFormula("smartmontools")),
    (BuildTools, BrewFormula("cmake")),
    (FfmpegFull, BrewFormula("ffmpeg")),
]


@pytest.mark.parametrize(("cls", "cask"), CASK_APPS)
def test_gui_apps_install_their_cask(cls: type[FlatpakApp], cask: str) -> None:
    assert cls.cask == cask
    ex = FakeExecutor(scripts={"brew": Result(1)})  # not installed yet
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    # PD3: Brew.install_cask raises on a non-zero exit, so the install half uses a plain
    # FakeExecutor (defaults every call to Result(0)) rather than the verify half's Result(1).
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["brew", "install", "--cask", "-y", "--adopt", cask]


@pytest.mark.parametrize(("cls", "strategy"), STRATEGIES)
def test_macos_goes_through_its_brew_strategy(cls: type[Module], strategy: Installer) -> None:
    assert cls.per_os.macos == strategy
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls[0][:2] == ["brew", "list"]  # brew decides, not `which`
    # PD3: Brew.install raises on a non-zero exit, so the install half uses a plain
    # FakeExecutor (defaults every call to Result(0)) rather than Result(1).
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1][:2] == ["brew", "install"]


def test_linux_paths_are_unchanged() -> None:
    ex = FakeExecutor()
    Mosh().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == [["sudo", "dnf", "install", "-y", "mosh"]]
    ex = FakeExecutor()
    Smartmontools().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "install", "-y", "smartmontools"] in ex.calls
    ex = FakeExecutor()
    FfmpegFull().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls[0][:3] == ["sudo", "dnf", "swap"]


def test_build_tools_needs_the_command_line_tools(tmp_path: Path) -> None:
    assert XcodeClt in BuildTools.requires
    plan = build_plan(["ffmpeg-full", "build-tools"], load(), MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {"ffmpeg-full": None, "build-tools": None}
