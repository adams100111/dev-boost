import pytest
from pathlib import Path

from devboost.manifest import Module, load_modules
from devboost.osinfo import OsInfo
from devboost.plan import resolve_steps
from devboost.profile import expand, load_profiles

ROOT = Path(__file__).resolve().parents[2]

UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def _profiles_and_modules() -> tuple[dict[str, list[str]], dict[str, Module]]:
    return load_profiles(ROOT / "profiles.toml"), load_modules(ROOT / "modules")


def _terminal_modules() -> list[tuple[str, Module]]:
    profs, mods = _profiles_and_modules()
    return [(n, mods[n]) for n in expand(["terminal"], profs, mods)]


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


@pytest.mark.parametrize("name", [n for n, _ in _terminal_modules()])
def test_every_terminal_module_resolves_on_ubuntu(name: str) -> None:
    profs, mods = _profiles_and_modules()
    steps = resolve_steps(mods[name], UBUNTU)
    assert steps, f"{name} resolves to no install step on Ubuntu (would be unsupported-os)"
