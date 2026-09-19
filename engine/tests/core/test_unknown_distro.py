"""An unrecognised Linux distro keeps bash-config; macOS reports it as platform-provided.

Before D11 ``BashConfig.families`` was the allow-list ``("fedora", "debian", "arch")``, so
an unknown distro — whose family is its own id (``osinfo.detect`` falls back to ``ID`` when
``ID_LIKE`` names nothing known) — silently lost its bash setup, and macOS dropped the
module without saying why. ``families = ()`` plus ``provided_by = ("macos",)`` keeps the
module everywhere on Linux and turns the macOS case into an explicit
``provided-by-macos`` skip (zsh-config covers it there).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.modules.shell import BashConfig

REPO_ROOT = Path(__file__).resolve().parents[3]

GENTOO = OsInfo("gentoo", "gentoo", "x86_64", headless=False)
MACOS = OsInfo("macos", "macos", "aarch64", headless=False)
FEDORA = OsInfo("fedora", "fedora", "x86_64", headless=False)
UBUNTU = OsInfo("ubuntu", "debian", "x86_64", headless=False, id_like=("debian",))
ARCH = OsInfo("arch", "arch", "x86_64", headless=False)


def _plan(profile: str, os_info: OsInfo, tmp_path: Path) -> list[PlannedModule]:
    modules = load()
    names = expand([profile], load_profiles(REPO_ROOT / "profiles.toml"), modules)
    return build_plan(toposort(names, modules), modules, os_info, gpu_marker=tmp_path / "none")


def _reason(profile: str, os_info: OsInfo, tmp_path: Path, name: str) -> str | None:
    reasons = {p.name: p.skip_reason for p in _plan(profile, os_info, tmp_path)}
    assert name in reasons, f"{name} missing from the {profile} plan on {os_info.distro}"
    return reasons[name]


def test_bash_config_is_not_family_scoped() -> None:
    assert BashConfig.families == ()
    assert BashConfig.provided_by == ("macos",)


def test_unknown_distro_keeps_bash_config(tmp_path: Path) -> None:
    assert _reason("shell", GENTOO, tmp_path, "bash-config") is None


def test_macos_reports_bash_config_provided(tmp_path: Path) -> None:
    assert _reason("shell", MACOS, tmp_path, "bash-config") == "provided-by-macos"


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH], ids=["fedora", "debian", "arch"])
def test_known_linux_families_unchanged(os_info: OsInfo, tmp_path: Path) -> None:
    assert _reason("shell", os_info, tmp_path, "bash-config") is None


def test_unknown_distro_plan_has_no_unsupported_bash_config(tmp_path: Path) -> None:
    """The point of the change: nothing in the shell profile is dropped on an unknown
    distro just because its family is unrecognised."""
    reasons = {p.name: p.skip_reason for p in _plan("shell", GENTOO, tmp_path)}
    assert reasons.get("bash-config") is None
    assert reasons.get("dotfiles") is None
