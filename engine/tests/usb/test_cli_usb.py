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


def test_usb_dry_run_previews_without_building(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.usb as cli_usb
    from devboost.usb.probe import DiskState

    monkeypatch.setattr(cli_usb, "probe", lambda ctx, device: DiskState("blank"))

    called = {"build": False}
    monkeypatch.setattr(cli_usb, "build", lambda *a, **k: called.__setitem__("build", True))
    # Avoid a real HEAD request for the size note.
    monkeypatch.setattr(cli_usb, "_iso_note", lambda cfg: "≈2.0 GB")

    result = runner.invoke(
        app, ["usb", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "/dev/sdb" in clean and "build" in clean
    assert called["build"] is False
