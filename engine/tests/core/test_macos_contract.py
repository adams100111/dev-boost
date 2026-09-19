"""Every module must have a macOS answer: installable, dropped, provided, or a known gap.

KNOWN_GAPS maps each module with no macOS path yet to the milestone that brings it
(spec §11). M2 cleared the terminal set and M3 the catalog; what is left is the Docker
runtime and the launchd timers (M4, each declared `MacosPending`). A new module must
arrive with its macOS answer; the map must be empty by the end of M5 (§9).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pending import MacosPending
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp
from tests.conftest import HOST_APP_PATHS

KNOWN_GAPS: dict[str, str] = {
    "aspire-gc": "M4",
    "docker": "M4",
    "docker-build-gc": "M4",
    "obsidian-sync": "M4",
    "restic-b2": "M4",
    "restic-backup": "M4",
}


def resolvable_on_macos(cls: type[Module]) -> bool:
    if cls.families and "macos" not in cls.families:
        return True  # dropped from the plan on macOS
    if "macos" in cls.provided_by:
        return True
    if isinstance(cls.per_os.macos, MacosPending):
        return False  # designed, but owned by a later milestone: still a known gap
    if cls.per_os.macos is not None:
        return True
    if issubclass(cls, PackageModule):
        # Only the base behaviour is brew-aware; a subclass that overrides install/verify
        # (COPR, curl installers, …) needs its own macOS answer.
        return cls.install is PackageModule.install and cls.verify is PackageModule.verify
    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    return cls.portable


def unresolved() -> set[str]:
    return {name for name, cls in load().items() if not resolvable_on_macos(cls)}


def test_no_new_macos_gaps() -> None:
    new = unresolved() - set(KNOWN_GAPS)
    msg = f"modules with no macOS path (add per_os.macos / families / cask): {sorted(new)}"
    assert not new, msg


def test_known_gaps_are_still_gaps() -> None:
    fixed = set(KNOWN_GAPS) - unresolved()
    assert not fixed, f"now resolvable — remove from KNOWN_GAPS: {sorted(fixed)}"


def test_later_milestone_gaps_are_the_pending_modules() -> None:
    # A gap owned by a later milestone must say so on a Mac (MacosPending), never fall
    # through to its Linux path; and every MacosPending module is listed under its owner.
    pending = {
        name: cls.per_os.macos.milestone for name, cls in load().items()
        if isinstance(cls.per_os.macos, MacosPending)
    }
    assert pending == KNOWN_GAPS


REPO_ROOT = Path(__file__).resolve().parents[3]
MAC = OsInfo("macos", "macos", "aarch64", headless=False)
FEDORA = OsInfo("fedora", "fedora", "x86_64", headless=False)


def _plan(profile: str, os_info: OsInfo, tmp_path: Path) -> list[PlannedModule]:
    modules = load()
    names = expand([profile], load_profiles(REPO_ROOT / "profiles.toml"), modules)
    return build_plan(toposort(names, modules), modules, os_info, gpu_marker=tmp_path / "none")


def test_known_gaps_have_an_owner() -> None:
    # M3 closed the catalog: every gap left is the Docker runtime / launchd timers (C-R8a).
    assert set(KNOWN_GAPS.values()) == {"M4"}


def test_the_macos_profile_plans_the_workstation(tmp_path: Path) -> None:
    modules = load()
    reasons = {p.name: p.skip_reason for p in _plan("macos", MAC, tmp_path)}
    gaps = {n for n in reasons if not resolvable_on_macos(modules[n])}
    assert gaps <= set(KNOWN_GAPS), sorted(gaps - set(KNOWN_GAPS))
    assert not [n for n, r in reasons.items() if r == "unsupported-os"]
    for want in (
        "xcode-clt", "homebrew", "rosetta", "zed", "fresh", "herdr", "herdr-plugins", "glow",
        "dotnet-sdk", "aspire", "android-sdk", "expo", "ddev", "uv", "web-runtimes",
        "tailscale", "mosh", "obsidian", "bruno", "claude-code", "codex-code", "pi-harness",
        "ghostty", "zsh-config", "dotfiles", "pass", "pass-store", "utiluti",
    ):
        assert reasons.get(want, "missing") is None, want
    assert reasons["flameshot"] == reasons["curl"] == "provided-by-macos"
    for gone in ("gearlever", "rpmfusion", "flatpak", "bash-config", "wezterm"):
        assert gone not in reasons, gone


def test_the_macos_profile_covers_the_terminal_set(tmp_path: Path) -> None:
    mac = {p.name for p in _plan("macos", MAC, tmp_path)}
    assert {p.name for p in _plan("terminal", MAC, tmp_path)} <= mac


def test_the_linux_workstation_gains_only_glow_and_herdr_plugins(tmp_path: Path) -> None:
    names = {p.name for p in _plan("full", FEDORA, tmp_path)}
    assert {"glow", "herdr-plugins"} <= names
    assert not {"xcode-clt", "homebrew", "rosetta", "utiluti", "zsh-config"} & names


def test_the_terminal_profile_still_plans_cleanly_on_fedora(tmp_path: Path) -> None:
    reasons = {p.name: p.skip_reason for p in _plan("terminal", FEDORA, tmp_path)}
    assert not {n: r for n, r in reasons.items() if r is not None}
    assert "bash-config" in reasons and "ghostty" in reasons
    assert not {"zsh-config", "zsh-plugins", "bash"} & set(reasons)


# --- hermeticity: no test reads the host's /Applications ------------------------------

_SRC = Path(__file__).resolve().parents[2] / "src"
_APP_CONST = re.compile(
    r'^(\w+)\s*(?::[^=\n]*)?=\s*Path\(\s*"/Applications/[^"]+\.app"\s*\)', re.M
)


def _app_constants_in_src() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for py in _SRC.rglob("*.py"):
        module = ".".join(py.relative_to(_SRC).with_suffix("").parts)
        found |= {(module, m) for m in _APP_CONST.findall(py.read_text(encoding="utf-8"))}
    return found


def test_every_app_bundle_constant_is_neutralised_in_tests() -> None:
    # B2 review: a new `/Applications/*.app` probe must be added to conftest's
    # HOST_APP_PATHS, or the suite would silently depend on what this Mac has installed.
    found = _app_constants_in_src()
    assert found, "the scan found nothing: the pattern no longer matches the sources"
    assert found == set(HOST_APP_PATHS)


def test_the_app_bundle_constants_point_nowhere(tmp_path: Path) -> None:
    for name, attr in HOST_APP_PATHS:
        path = getattr(importlib.import_module(name), attr)
        assert path.is_relative_to(tmp_path) and not path.exists(), (name, attr)
