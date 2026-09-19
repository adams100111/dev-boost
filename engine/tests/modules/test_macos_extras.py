"""macos-extras (opt-in casks). `profiles.toml`'s `macos-extras` member list is filled by
the integration lane (lanes.md §2: `profiles.toml` is an owner-only file, not M5-C's) — the
second test below pins the intended membership against `expand()` directly instead of
reading the real (still-empty) `[profiles]` table, so I-M5 has the exact list to paste in.
"""

from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.modules._brew import BrewCask
from devboost.modules._cask import CaskApp, CaskInstall
from devboost.modules.shell import Wezterm

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]

EXTRAS = {
    # module: (cask, launch, TCC services)
    "maccy": ("maccy", "Maccy", ("Accessibility",)),
    "ollama-app": ("ollama-app", None, ()),
    "lm-studio": ("lm-studio", None, ()),
    "pearcleaner": ("pearcleaner", None, ()),
    "keycastr": ("keycastr", None, ("ListenEvent", "Accessibility")),
    "linearmouse": ("linearmouse", "LinearMouse", ("Accessibility",)),
    "android-studio": ("android-studio", None, ()),
    "expo-orbit": ("expo-orbit", None, ()),
    "herd": ("herd", None, ()),
}


def test_extras_cask_table() -> None:
    mods = load()
    for name, (cask, launch, services) in EXTRAS.items():
        cls = mods[name]
        assert issubclass(cls, CaskApp), name
        assert cls.per_os.macos == CaskInstall(cask, launch), name
        assert tuple(g.service for g in cls.tcc) == services, name
        assert cls.profiles == ("macos-extras",), name


def test_macos_extras_profile_would_be_the_extras_plus_wezterm() -> None:
    modules = load()
    assert "wezterm" in modules
    fake_profiles = {"macos-extras": [*EXTRAS, "wezterm"]}
    got = expand(["macos-extras"], fake_profiles, modules)
    assert got == [*EXTRAS, "wezterm"]


def test_wezterm_in_macos_extras_pulls_nothing_linux_only(tmp_path: Path) -> None:
    """Minor 6: `wezterm` is cross-OS (no `families`): the nightly cask on macOS, the
    AppImage on Linux via `optional-terminals`. Its `macos-extras` membership adds no
    Linux behaviour: on a Mac it plans the cask (plus Homebrew), and on Linux the profile
    plans exactly what `optional-terminals` already does — every other extra drops out."""
    modules = load()
    profiles = load_profiles(REPO_ROOT / "profiles.toml")

    def runnable(profile: str, os_info: OsInfo) -> set[str]:
        order = toposort(expand([profile], profiles, modules), modules)
        plan = build_plan(order, modules, os_info, gpu_marker=tmp_path / "none")
        return {p.name for p in plan if p.skip_reason is None}

    assert runnable("macos-extras", FEDORA) == runnable("optional-terminals", FEDORA) == {
        "wezterm"
    }
    assert isinstance(Wezterm.per_os.macos, BrewCask)  # macOS never takes the AppImage path
    assert {"wezterm", "homebrew", *EXTRAS} <= runnable("macos-extras", MAC)
