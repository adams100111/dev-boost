"""macos-extras (opt-in casks). `profiles.toml`'s `macos-extras` member list is filled by
the integration lane (lanes.md §2: `profiles.toml` is an owner-only file, not M5-C's) — the
second test below pins the intended membership against `expand()` directly instead of
reading the real (still-empty) `[profiles]` table, so I-M5 has the exact list to paste in.
"""

from __future__ import annotations

from devboost.core.profiles import expand
from devboost.core.registry import load
from devboost.modules._cask import CaskApp, CaskInstall

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
