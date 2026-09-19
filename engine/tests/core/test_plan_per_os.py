"""per_os entries decide on their OS; a module's own install() covers the rest."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.plan import build_plan
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")


class _OwnInstall(Module):
    name: ClassVar[str] = "own-install-probe"
    per_os = OsMap(macos=BrewFormula("probe"))

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


class _StrategyOnly(Module):
    name: ClassVar[str] = "strategy-only-probe"
    per_os = OsMap(macos=BrewFormula("probe"))


MODULES: dict[str, type[Module]] = {
    "own-install-probe": _OwnInstall,
    "strategy-only-probe": _StrategyOnly,
}


def test_own_install_is_the_fallback_off_the_declared_os(tmp_path: Path) -> None:
    plan = build_plan(list(MODULES), MODULES, FEDORA, gpu_marker=tmp_path / "none")
    assert {p.name: p.skip_reason for p in plan} == {
        "own-install-probe": None,
        "strategy-only-probe": "unsupported-os",
    }


def test_declared_os_is_supported_for_both(tmp_path: Path) -> None:
    plan = build_plan(list(MODULES), MODULES, MAC, gpu_marker=tmp_path / "none")
    assert {p.name: p.skip_reason for p in plan} == {
        "own-install-probe": None,
        "strategy-only-probe": None,
    }
