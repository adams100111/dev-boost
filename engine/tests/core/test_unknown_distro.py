"""An unrecognised Linux distro keeps bash-config; macOS reports it as platform-provided.

Before D11 ``BashConfig.families`` was the allow-list ``("fedora", "debian", "arch")``, so
an unknown distro — whose family is its own id (``osinfo.detect`` falls back to ``ID`` when
``ID_LIKE`` names nothing known) — silently lost its bash setup, and macOS dropped the
module without saying why. ``families = ()`` plus ``provided_by = ("macos",)`` keeps the
module everywhere on Linux and turns the macOS case into an explicit
``provided-by-macos`` skip (zsh-config covers it there).

(The class attributes themselves are asserted by
``tests/modules/test_zsh_modules.py::test_bash_config_is_planned_everywhere_but_provided_by_macos``;
this file tests what ``build_plan`` and the module do with them.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
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


def test_unknown_distro_keeps_bash_config(tmp_path: Path) -> None:
    reasons = {p.name: p.skip_reason for p in _plan("shell", GENTOO, tmp_path)}
    assert reasons.get("bash-config", "missing") is None
    assert reasons.get("dotfiles", "missing") is None  # its dependency plans too


def test_macos_reports_bash_config_provided(tmp_path: Path) -> None:
    assert _reason("shell", MACOS, tmp_path, "bash-config") == "provided-by-macos"


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH], ids=["fedora", "debian", "arch"])
def test_known_linux_families_unchanged(os_info: OsInfo, tmp_path: Path) -> None:
    assert _reason("shell", os_info, tmp_path, "bash-config") is None


def test_bash_config_fails_loudly_when_an_unknown_distro_owns_bashrc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flip side of D11: bash-config now actually *runs* on an unrecognised distro.

    ``_owns_bashrc`` special-cases only Omarchy, so anywhere else the module assumes
    dev-boost's dotfiles wrote ``~/.bashrc`` and ``install`` is a marker check. On a distro
    that ships its own ``~/.bashrc`` and whose package owns the file, chezmoi leaves it
    alone, so ``verify`` stays False after ``install`` and the runner reports
    ``verify failed after install`` — a loud failure where D11's predecessor produced a
    silent drop. That is the intended trade: visible over invisible.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = Ctx(os=GENTOO, ex=FakeExecutor())
    bashrc = tmp_path / ".bashrc"
    distro_owned = "# /etc/skel/.bashrc, shipped by the distro\nPS1='$ '\n"
    bashrc.write_text(distro_owned, encoding="utf-8")

    assert BashConfig()._owns_bashrc(ctx) is True  # not Omarchy: dotfiles own the file
    assert BashConfig().verify(ctx) is False
    BashConfig().install(ctx)  # a no-op marker check, not an append
    assert bashrc.read_text(encoding="utf-8") == distro_owned
    assert BashConfig().verify(ctx) is False  # → the runner fails the module, loudly
