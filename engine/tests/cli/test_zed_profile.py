from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def _expand(*tokens: str) -> list[str]:
    return expand(list(tokens), load_profiles(REPO_ROOT / "profiles.toml"), load())


def test_editors_profile_is_zed_fresh_fresh_lsp() -> None:
    assert _expand("editors") == ["zed", "fresh", "fresh-lsp"]


def test_vscode_moves_to_optional_editors() -> None:
    assert "vscode" in _expand("optional-editors")
    assert "vscode" not in _expand("full")
    assert "vscode" not in _expand("omarchy")


def test_zed_is_in_full_and_omarchy() -> None:
    assert "zed" in _expand("full")
    assert "zed" in _expand("omarchy")
