"""Pins the M5 profile shape (spec §9): the desktop/ios/extras opt-in sets, `voxtype`
in every default, and a clean Mac plan for the macos-only sets on Linux.
"""

from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _expand(*tokens: str) -> list[str]:
    return expand(list(tokens), load_profiles(REPO_ROOT / "profiles.toml"), load())


def test_macos_desktop_members() -> None:
    # M5-D2: `default-apps` (duti) was dropped — code files open in Zed via `Utiluti`.
    assert _expand("macos-desktop") == [
        "macos-defaults", "macos-limits", "macos-firewall", "timemachine-exclusions",
        "stats", "raycast", "aerospace", "alt-tab", "thaw", "monitorcontrol", "keka",
        "quicklook",
    ]


def test_ios_members() -> None:
    assert _expand("ios") == ["xcode", "ios-tooling"]


def test_macos_includes_the_desktop() -> None:
    mac = set(_expand("macos"))
    assert set(_expand("macos-desktop")) <= mac


def test_voxtype_is_opt_in_everywhere() -> None:
    """Dictation is an application preference, not toolchain. It also costs a 488 MB
    model, three privacy grants and a Login Item, and is the one module that cannot
    finish unattended — so no default profile may pull it in."""
    for aggregate in ("base", "full", "omarchy", "macos"):
        assert "voxtype" not in _expand(aggregate), aggregate


def test_opt_ins_stay_out_of_every_default() -> None:
    for aggregate in ("full", "omarchy", "macos"):
        got = set(_expand(aggregate))
        opt_ins = {"voxtype", "voxtype-arabic", "android-emulator", "xcode", "maccy"}
        assert not opt_ins & got, aggregate


def test_linux_drops_the_mac_only_sets(tmp_path: Path) -> None:
    mods = load()
    mac_only = _expand("macos-desktop", "ios")
    order = toposort(mac_only, mods)  # also pulls cross-OS requirements such as `zed`
    planned = {p.name for p in build_plan(order, mods, FEDORA, gpu_marker=tmp_path / "none")}
    assert not planned & set(mac_only)
    assert "homebrew" not in planned
