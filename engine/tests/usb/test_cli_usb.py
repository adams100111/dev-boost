from __future__ import annotations

import re

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_usb_help_lists_the_command() -> None:
    result = runner.invoke(app, ["usb", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "--device" in clean and "--profile" in clean


def test_usb_no_wizard_requires_device() -> None:
    # --no-wizard with no --device should error out (exit 1), not prompt.
    result = runner.invoke(app, ["usb", "--no-wizard"])
    assert result.exit_code != 0
