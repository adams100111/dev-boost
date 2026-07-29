from __future__ import annotations

import pytest
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


def test_apply_update_filter_keeps_only_self_updating() -> None:
    from devboost.cli.app import _apply_update_filter
    from devboost.core.plan import PlannedModule
    from devboost.model import Module

    class Refreshable(Module):
        name = "refreshable"
        self_updating = True

    class Heavy(Module):
        name = "heavy"
        self_updating = False

    modules = {"refreshable": Refreshable, "heavy": Heavy}
    plan = [PlannedModule(name="refreshable"), PlannedModule(name="heavy")]

    kept = _apply_update_filter(plan, modules)

    assert [pm.name for pm in kept] == ["refreshable"]


def test_install_update_dry_run_filters_to_self_updating() -> None:
    # --dry-run lists "would install <name>" for the filtered plan only.
    result = runner.invoke(app, ["install", "--update", "--dry-run"])
    assert result.exit_code == 0
    assert "would install lazydocker" in result.output      # a self_updating tool: kept
    assert "would install git" in result.output             # a base package: kept (broad)
    assert "would install docker" not in result.output      # a heavy Module: dropped


def test_install_force_and_update_are_mutually_exclusive() -> None:
    result = runner.invoke(app, ["install", "--force", "--update"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_update_help_points_to_install_update() -> None:
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "install --update" in result.output


def test_install_update_forces_run_over_filtered_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--update forces the run (bypassing verify) over a plan filtered to self_updating tools."""
    captured: dict[str, object] = {}

    def fake_run_plan(plan, modules, ctx):  # type: ignore[no-untyped-def]
        captured["force"] = ctx.force
        captured["names"] = [pm.name for pm in plan]
        return []

    monkeypatch.setattr("devboost.cli.app.run_plan", fake_run_plan)
    result = runner.invoke(app, ["install", "--update"])
    assert result.exit_code == 0
    assert captured["force"] is True                # --update forces the kept tools
    assert "lazydocker" in captured["names"]        # a self_updating tool is kept
    assert "docker" not in captured["names"]        # a heavy Module is filtered out
