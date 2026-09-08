from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pi_profile_expands_to_pi_harness() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    assert expand(["pi"], profiles, modules) == ["pi-harness"]


def test_full_includes_pi_harness() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    assert "pi-harness" in expand(["full"], profiles, modules)
