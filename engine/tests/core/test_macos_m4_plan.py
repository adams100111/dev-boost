"""Every M4 module has a macOS answer and still plans on Fedora (spec §9 contract)."""

from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from tests.core.test_macos_contract import KNOWN_GAPS, resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
M4 = (
    "docker", "docker-build-gc", "ddev", "ddev-remote", "data-services", "aspire",
    "aspire-gc", "restic-backup", "restic-b2", "obsidian-sync", "browser-mcp",
)


def test_no_m4_module_is_a_known_gap() -> None:
    # M4-D11: KNOWN_GAPS is a dict; & needs a set on both sides.
    assert not set(M4) & set(KNOWN_GAPS)


def test_every_m4_module_resolves_on_macos() -> None:
    modules = load()
    assert [n for n in M4 if not resolvable_on_macos(modules[n])] == []


def test_the_m4_modules_plan_on_macos(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(list(M4), modules), modules, MAC, gpu_marker=tmp_path / "x")
    # Only the M4 modules themselves: a dependency may rightly be `provided-by-macos`.
    skipped = {p.name: p.skip_reason for p in plan if p.skip_reason and p.name in M4}
    assert skipped == {}
    assert set(M4) <= {p.name for p in plan}


def test_linux_keeps_its_timers_and_browser_mcp(tmp_path: Path) -> None:
    """C-M4-SEC2: browser-mcp now plans on Linux too — the module enables the systemd unit."""
    modules = load()
    plan = build_plan(toposort(list(M4), modules), modules, FEDORA, gpu_marker=tmp_path / "x")
    names = {p.name for p in plan if p.skip_reason is None}
    assert set(M4) <= names
    assert "homebrew" not in names
