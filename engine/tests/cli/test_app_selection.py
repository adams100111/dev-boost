from __future__ import annotations

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_term_command_exists_and_terminal_removed() -> None:
    names = {c.name for c in app.registered_commands}
    assert "term" in names
    assert "terminal" not in names


def test_term_exposes_all_and_app_flags() -> None:
    """`term` must offer --all/--no-all and --app.

    Asserted against Typer's parameter model, not the rendered --help panel. The old test
    grepped the panel text and passed locally while failing in CI for 20+ runs: Rich's
    layout depends on terminal width, its own version, and how it elides a long
    `[default: <root>]` — none of which is what this test is about. Grepping a renderer for
    a contract it does not own is a test of the renderer.
    """
    import typer.main

    cmd = next(c for c in app.registered_commands if c.name == "term")
    click_cmd = typer.main.get_command_from_info(
        cmd, pretty_exceptions_short=False, rich_markup_mode="rich"
    )
    opts = {o for p in click_cmd.params for o in (*p.opts, *p.secondary_opts)}
    assert {"--all", "-a", "--no-all", "--app"} <= opts


def test_term_help_renders_without_error() -> None:
    """--help must still work; what it looks like is Rich's business, not ours."""
    result = runner.invoke(app, ["term", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_term_unknown_app_exits_nonzero_with_suggestion() -> None:
    # --app against the terminal profile; 'gti' is unknown -> exit 2 + suggestion.
    result = runner.invoke(app, ["term", "--app", "gti", "--dry-run"])
    assert result.exit_code == 2
    assert "unknown app 'gti'" in (result.output + str(result.stderr_bytes or b""))
