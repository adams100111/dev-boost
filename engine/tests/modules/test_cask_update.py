"""`--update` upgrades Homebrew casks, except apps that update themselves (spec §6)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from devboost.cli.app import _apply_update_filter, _brew_managed_on_macos
from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.plan import PlannedModule
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp
from devboost.modules.base import Flatpak
from devboost.modules.macos import Homebrew

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Brew(FakeExecutor):
    """Scripted brew: `list` succeeds for installed casks, `info` reports auto_updates."""

    def __init__(self, installed: set[str], auto_updates: set[str] | None = None) -> None:
        super().__init__()
        self.installed = installed
        self.auto_updates = auto_updates or set()

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:2]) == ["brew", "list"]:
            return Result(0) if argv[-1] in self.installed else Result(1)
        if list(argv[:2]) == ["brew", "info"]:
            cask = argv[-1]
            body = {"casks": [{"token": cask, "auto_updates": cask in self.auto_updates}]}
            return Result(0, stdout=json.dumps(body))
        return Result(0)


def test_upgrade_cask_argv_and_failure() -> None:
    ex = FakeExecutor()
    pkg.upgrade_cask(Ctx(os=MAC, ex=ex), "localsend")
    assert ex.calls == [["brew", "upgrade", "--cask", "localsend"]]
    failing = FakeExecutor(scripts={"brew": Result(1)})
    with pytest.raises(InstallError, match="brew upgrade --cask localsend"):
        pkg.upgrade_cask(Ctx(os=MAC, ex=failing), "localsend")
    with pytest.raises(UnsupportedOS):
        pkg.upgrade_cask(Ctx(os=FEDORA, ex=FakeExecutor()), "localsend")


def test_cask_auto_updates_reads_brew_info() -> None:
    ex = _Brew(installed={"zed"}, auto_updates={"zed"})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=ex), "zed") is True
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=_Brew(installed=set())), "vlc") is False
    garbage = FakeExecutor(scripts={"brew": Result(0, stdout="not json")})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=garbage), "vlc") is False
    assert pkg.cask_auto_updates(Ctx(os=FEDORA, ex=FakeExecutor()), "vlc") is False


def test_force_upgrades_an_installed_cask_that_does_not_update_itself() -> None:
    ex = _Brew(installed={"localsend"})
    BrewCask("localsend").install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--cask", "localsend"]
    assert not any(c[:2] == ["brew", "install"] for c in ex.calls)


def test_force_leaves_a_self_updating_cask_alone() -> None:
    # A NAMED `brew upgrade --cask` is greedy in Homebrew 7 — it must not be called here.
    ex = _Brew(installed={"obsidian"}, auto_updates={"obsidian"})
    BrewCask("obsidian").install(Ctx(os=MAC, ex=ex, force=True))
    assert not any(c[:2] == ["brew", "upgrade"] for c in ex.calls)


def test_without_force_it_is_one_adopting_install() -> None:
    # Unchanged from M1/M2: installing an installed cask is a no-op in brew.
    ex = _Brew(installed={"vlc"})
    BrewCask("vlc").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "vlc"]]


def test_missing_cask_is_installed_even_under_force() -> None:
    ex = _Brew(installed=set())
    BrewCask("vlc").install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "install", "--cask", "-y", "--adopt", "vlc"]


def test_strategies_declare_they_use_brew() -> None:
    assert BrewCask.uses_brew is True
    assert BrewFormula.uses_brew is True


class _App(FlatpakApp):
    name: ClassVar[str] = "cask-update-probe"
    app_id: ClassVar[str] = "org.probe.App"
    cask: ClassVar[str | None] = "probe-app"


def test_flatpak_app_upgrades_its_cask_under_force() -> None:
    ex = _Brew(installed={"probe-app"})
    _App().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--cask", "probe-app"]


class _Custom(Module):
    name: ClassVar[str] = "custom-probe"
    per_os = OsMap(macos=BrewFormula("probe"))

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


class _Heavy(Module):
    name: ClassVar[str] = "heavy-probe"


def test_update_keeps_brew_backed_modules_on_macos_only() -> None:
    modules: dict[str, type[Module]] = {
        "cask-update-probe": _App, "custom-probe": _Custom, "heavy-probe": _Heavy,
    }
    plan = [PlannedModule(n) for n in modules]
    assert [p.name for p in _apply_update_filter(plan, modules, MAC)] == [
        "cask-update-probe", "custom-probe",
    ]
    assert _apply_update_filter(plan, modules, FEDORA) == []
    assert _apply_update_filter(plan, modules) == []  # no OS given: today's behaviour
    assert _brew_managed_on_macos(_Heavy) is False


def test_cask_auto_updates_falls_back_to_false_when_brew_fails_or_knows_no_cask() -> None:
    # False → the caller upgrades: at worst a needless re-download, never a stale app.
    failing = FakeExecutor(scripts={"brew": Result(1, stderr="Error: No available cask")})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=failing), "vlc") is False
    empty = FakeExecutor(scripts={"brew": Result(0, stdout='{"formulae": [], "casks": []}')})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=empty), "vlc") is False


class _Pkg(PackageModule):
    name: ClassVar[str] = "pkg-update-probe"
    cmd: ClassVar[str] = "probe"
    fedora_pkg: ClassVar[str] = "probe"


class _NoCaskApp(FlatpakApp):
    name: ClassVar[str] = "no-cask-probe"
    app_id: ClassVar[str] = "org.probe.NoCask"


def test_update_filter_keeps_package_modules_and_drops_caskless_apps_on_macos() -> None:
    # A PackageModule is one formula (or cask) on macOS: refreshed. A FlatpakApp with no
    # cask has nothing brew could upgrade there: dropped.
    assert _brew_managed_on_macos(_Pkg) is True
    assert _brew_managed_on_macos(_NoCaskApp) is False
    modules: dict[str, type[Module]] = {"pkg-update-probe": _Pkg, "no-cask-probe": _NoCaskApp}
    plan = [PlannedModule(n) for n in modules]
    assert [p.name for p in _apply_update_filter(plan, modules, MAC)] == ["pkg-update-probe"]


def test_a_caskless_app_does_not_require_homebrew() -> None:
    # Homebrew (and the CLT under it) only matter for installing a cask.
    assert Homebrew not in _NoCaskApp.requires and Flatpak in _NoCaskApp.requires
    assert Homebrew in _App.requires and Flatpak in _App.requires
