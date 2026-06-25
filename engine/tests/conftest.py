from pathlib import Path

import pytest


@pytest.fixture
def modules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "fzf.toml").write_text(
        'name = "fzf"\ncategory = "cli"\nverify = "command -v fzf"\n'
        '[install]\nfedora = "sudo dnf install -y fzf"\n'
        'debian = "sudo apt-get install -y fzf"\n'
    )
    eza = d / "eza"
    eza.mkdir()
    (eza / "module.toml").write_text(
        'name = "eza"\ncategory = "cli"\nverify = "command -v eza"\nrequires = ["fzf"]\n'
        '[install]\nfedora = "sudo dnf install -y eza"\n'
        '[fallback]\nmise = "aqua:eza-community/eza"\n'
    )
    ghostty = d / "ghostty"
    ghostty.mkdir()
    (ghostty / "module.toml").write_text(
        'name = "ghostty"\ncategory = "shell"\ngui = true\nverify = "command -v ghostty"\n'
        '[install]\nfedora = "echo install-ghostty"\n'
    )
    return d
