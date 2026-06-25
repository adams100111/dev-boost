import pytest
from pathlib import Path

from devboost.manifest import Module, load_modules
from devboost.profile import expand, load_profiles

ROOT = Path(__file__).resolve().parents[2]


def _profiles_and_modules() -> tuple[dict[str, list[str]], dict[str, Module]]:
    return load_profiles(ROOT / "profiles.toml"), load_modules(ROOT / "modules")


def test_terminal_excludes_secrets() -> None:
    profs, mods = _profiles_and_modules()
    resolved = expand(["terminal"], profs, mods)
    assert "secrets" not in resolved
    assert "chezmoi" in resolved and "dotfiles" in resolved


def test_devtools_includes_docker_via_ddev() -> None:
    profs, mods = _profiles_and_modules()
    resolved = expand(["devtools"], profs, mods)
    assert "docker" in resolved
    assert "debian" in mods["docker"].install
