from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from devboost import __version__
from devboost.cli.app import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_list_resolves_order(profiles_file: Path) -> None:
    result = runner.invoke(app, ["list", "laravel", "--root", str(profiles_file.parent)])
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert lines.index("docker") < lines.index("ddev")


def test_install_dry_run_no_side_effects(profiles_file: Path) -> None:
    result = runner.invoke(
        app, ["install", "cli", "--root", str(profiles_file.parent), "--dry-run"]
    )
    assert result.exit_code == 0


def test_unknown_profile_exits_nonzero(profiles_file: Path) -> None:
    result = runner.invoke(app, ["list", "nope", "--root", str(profiles_file.parent)])
    assert result.exit_code != 0
