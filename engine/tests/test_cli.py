from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


@pytest.fixture
def repo(modules_dir: Path) -> Path:
    root = modules_dir.parent
    (root / "profiles.toml").write_text(
        '[profiles]\nterminal = ["eza", "ghostty"]\ndevtools = ["fzf"]\n'
    )
    return root


def test_list_resolves_order(repo: Path) -> None:
    result = runner.invoke(app, ["list", "terminal", "--root", str(repo)])
    assert result.exit_code == 0
    # eza requires fzf -> fzf precedes eza; ghostty present
    out = result.stdout
    assert out.index("fzf") < out.index("eza")
    assert "ghostty" in out


def test_terminal_dry_run(repo: Path) -> None:
    result = runner.invoke(app, ["terminal", "--dry-run", "--root", str(repo)])
    assert result.exit_code == 0
    assert "would install" in result.stdout


def test_terminal_dry_run_skips_gui_when_headless(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    result = runner.invoke(app, ["terminal", "--dry-run", "--root", str(repo)])
    assert "skip ghostty (headless-gui)" in result.stdout


def test_unknown_profile_clean_error(repo: Path) -> None:
    result = runner.invoke(app, ["list", "nope-not-a-profile", "--root", str(repo)])
    assert result.exit_code == 1
    assert "error:" in result.output
    # no raw traceback leaked
    assert "Traceback" not in result.output


def test_default_root_honors_devboost_root_env(monkeypatch, tmp_path) -> None:
    import importlib
    monkeypatch.setenv("DEVBOOST_ROOT", str(tmp_path))
    import devboost.cli as climod
    importlib.reload(climod)
    assert climod._DEFAULT_ROOT == tmp_path
    monkeypatch.delenv("DEVBOOST_ROOT")
    importlib.reload(climod)
    assert climod._DEFAULT_ROOT.name == "dev-boost" or climod._DEFAULT_ROOT.exists()
