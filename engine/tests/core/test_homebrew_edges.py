"""Homebrew (and so the CLT) is installed before anything that installs through brew."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli.app import _added_dependencies
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
#: A path that never exists, so the GPU auto-inject in build_plan() is a deterministic
#: no-op at collection time (host state must not change which modules get parametrized).
_NO_GPU_MARKER = Path("/nonexistent-devboost-gpu-marker")


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
    """Static check: read off `per_os`/base-class shape. Kept alongside the behavioural
    test below, which catches a module that calls brew from its own install() without
    declaring a per_os.macos strategy (the static check only looks there)."""
    modules = load()
    missing = sorted(
        name for name, cls in modules.items()
        if macos_uses_brew(cls) and "homebrew" not in toposort([name], modules)
    )
    assert not missing, f"add Homebrew to `requires` of: {missing}"


def _planned_on_macos() -> list[str]:
    """Every registered module build_plan would actually run on a Mac (no skip_reason)."""
    modules = load()
    order = toposort(list(modules), modules)
    plan = build_plan(order, modules, MAC, gpu_marker=_NO_GPU_MARKER)
    return sorted(p.name for p in plan if p.skip_reason is None)


@pytest.mark.parametrize("name", _planned_on_macos())
def test_a_module_that_calls_brew_requires_homebrew(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavioural version of the static check above (ruling C-R19): actually run
    install() under a fake macOS executor and look at what it called. This is what
    caught `pass` and `secrets` — direct `pkg.install`/`install_cask` calls made from
    inside a portable module's own install(), invisible to a per_os-only static check.
    """
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    modules = load()
    cls = modules[name]
    ex = FakeExecutor()
    try:
        cls().install(Ctx(os=MAC, ex=ex))
    except Exception:  # noqa: BLE001 — every outcome is fine, only the calls matter
        pass
    if any(call and call[0] == "brew" for call in ex.calls):
        assert "homebrew" in toposort([name], modules), (
            f"{name} runs brew from install() but doesn't require Homebrew"
        )


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
