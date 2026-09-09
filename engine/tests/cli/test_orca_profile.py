from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_orca_profiles_expand() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    assert expand(["orca"], profiles, modules) == ["orca-ide"]
    assert expand(["orca-box"], profiles, modules) == ["orca-ide", "orca-serve"]
