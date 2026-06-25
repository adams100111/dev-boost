from pathlib import Path

import pytest

from devboost.manifest import ManifestError, Module, load_modules


def test_loads_simple_and_dir_modules(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    assert set(mods) == {"fzf", "eza", "ghostty"}
    assert mods["eza"].requires == ("fzf",)
    assert mods["eza"].fallback == {"mise": "aqua:eza-community/eza"}
    assert mods["ghostty"].gui is True
    assert mods["fzf"].install["debian"] == "sudo apt-get install -y fzf"


def test_missing_verify_raises(tmp_path: Path) -> None:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "bad.toml").write_text('name = "bad"\ncategory = "cli"\n[install]\nfedora = "x"\n')
    with pytest.raises(ManifestError, match="bad.*verify"):
        load_modules(d)


def test_no_install_path_raises(tmp_path: Path) -> None:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "bad.toml").write_text('name = "bad"\ncategory = "cli"\nverify = "true"\n')
    with pytest.raises(ManifestError, match="bad.*install"):
        load_modules(d)
