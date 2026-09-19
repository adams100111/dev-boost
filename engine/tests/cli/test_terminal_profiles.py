from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_ghostty_is_the_default_terminal_and_wezterm_is_opt_in() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    for name in ("shell", "terminal", "full", "omarchy"):
        members = expand([name], profiles, modules)
        assert "ghostty" in members, name
        assert "wezterm" not in members, name
    assert expand(["optional-terminals"], profiles, modules) == ["wezterm"]
