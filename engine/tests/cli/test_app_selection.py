from __future__ import annotations

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_term_command_exists_and_terminal_removed() -> None:
    names = {c.name for c in app.registered_commands}
    assert "term" in names
    assert "terminal" not in names


def test_term_help_lists_all_and_app_flags() -> None:
    result = runner.invoke(app, ["term", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output
    assert "--no-all" in result.output
    assert "--app" in result.output


def test_term_unknown_app_exits_nonzero_with_suggestion() -> None:
    # --app against the terminal profile; 'gti' is unknown -> exit 2 + suggestion.
    result = runner.invoke(app, ["term", "--app", "gti", "--dry-run"])
    assert result.exit_code == 2
    assert "unknown app 'gti'" in (result.output + str(result.stderr_bytes or b""))
