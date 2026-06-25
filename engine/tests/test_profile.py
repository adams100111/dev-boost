from pathlib import Path

from devboost.manifest import load_modules
from devboost.profile import expand, load_profiles


def test_load_profiles(tmp_path: Path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text('[profiles]\nterminal = ["eza"]\ndevtools = ["fzf"]\n')
    profs = load_profiles(p)
    assert profs["terminal"] == ["eza"]


def test_expand_profile_pulls_requires(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    profiles = {"terminal": ["eza"]}
    # eza requires fzf -> fzf must appear, before eza
    result = expand(["terminal"], profiles, mods)
    assert result == ["fzf", "eza"]


def test_expand_dedupes_and_accepts_bare_module(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    result = expand(["fzf", "eza"], {}, mods)
    assert result == ["fzf", "eza"]


def test_expand_raises_on_requires_cycle() -> None:
    from devboost.graph import DependencyCycle
    from devboost.manifest import Module

    def _m(name: str, requires: tuple[str, ...]) -> Module:
        return Module(name, "cli", "true", requires, {"fedora": "x"}, {}, False)

    mods = {"a": _m("a", ("b",)), "b": _m("b", ("a",))}
    import pytest
    with pytest.raises(DependencyCycle):
        expand(["a"], {}, mods)
