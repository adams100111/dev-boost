from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_claude_profile_expands_to_the_four_modules() -> None:
    modules = load()  # dict[str, type[Module]] — confirmed in core/registry.py:31
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    resolved = expand(["claude"], profiles, modules)
    names = {r if isinstance(r, str) else getattr(r, "name", None) for r in resolved}
    assert {"claude-code", "claude-plugins", "claude-skills", "claude-mcp"} <= names
