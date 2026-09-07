from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_codex_profile_expands_to_the_five_modules() -> None:
    modules = load()
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    resolved = expand(["codex"], profiles, modules)
    names = {r if isinstance(r, str) else getattr(r, "name", None) for r in resolved}
    assert {"codex-code", "codex-config", "codex-plugins", "codex-mcp", "codex-skills"} <= names
