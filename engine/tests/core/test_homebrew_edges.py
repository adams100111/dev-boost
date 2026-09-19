"""Homebrew (and so the CLT) is installed before anything that installs through brew."""

from __future__ import annotations

from pathlib import Path

from devboost.cli.app import _added_dependencies
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def macos_uses_brew(cls: type[Module]) -> bool:
    """Does this module install through Homebrew when it runs on a Mac?"""
    if cls.families and "macos" not in cls.families:
        return False
    if "macos" in cls.provided_by:
        return False
    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    if issubclass(cls, PackageModule):
        return True
    return bool(getattr(cls.per_os.macos, "uses_brew", False))


def test_brew_backed_modules_require_homebrew() -> None:
    modules = load()
    missing = sorted(
        name for name, cls in modules.items()
        if macos_uses_brew(cls) and "homebrew" not in toposort([name], modules)
    )
    assert not missing, f"add Homebrew to `requires` of: {missing}"


def test_homebrew_and_the_clt_come_first_on_a_mac(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(["ripgrep", "jq"], modules), modules, MAC,
                      gpu_marker=tmp_path / "x")
    names = [p.name for p in plan]
    assert names.index("xcode-clt") < names.index("homebrew") < names.index("ripgrep")
    assert names.index("homebrew") < names.index("jq")


def test_linux_plans_never_carry_the_macos_foundation(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(["ripgrep", "jq", "vlc"], modules), modules, FEDORA,
                      gpu_marker=tmp_path / "x")
    assert not {"homebrew", "xcode-clt"} & {p.name for p in plan}


def test_the_dependency_log_names_planned_modules_only() -> None:
    plan = [PlannedModule("flatpak"), PlannedModule("vlc")]
    assert _added_dependencies(plan, ["vlc"]) == ["flatpak"]
