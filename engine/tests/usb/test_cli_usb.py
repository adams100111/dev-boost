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


def test_usb_yes_on_devboost_stick_updates_not_wipes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.usb as cli_usb
    from devboost.usb.marker import Marker
    from devboost.usb.probe import DiskState

    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    monkeypatch.setattr(cli_usb, "probe", lambda ctx, device: DiskState("devboost", marker))
    monkeypatch.setattr(cli_usb, "build", lambda *a, **k: None)
    monkeypatch.setattr(cli_usb, "_iso_note", lambda cfg: "cached")
    result = runner.invoke(
        app, ["usb", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "update" in clean  # --yes alone does NOT force a wipe on a dev-boost stick


def test_usb_rebuild_flag_forces_build_on_devboost_stick(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.usb as cli_usb
    from devboost.usb.marker import Marker
    from devboost.usb.probe import DiskState

    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    monkeypatch.setattr(cli_usb, "probe", lambda ctx, device: DiskState("devboost", marker))
    monkeypatch.setattr(cli_usb, "build", lambda *a, **k: None)
    monkeypatch.setattr(cli_usb, "_iso_note", lambda cfg: "cached")
    result = runner.invoke(
        app, ["usb", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--rebuild"]
    )
    assert result.exit_code == 0
    assert "build" in _strip_ansi(result.stdout)


def test_usb_unpinned_arch_exits_cleanly(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.usb as cli_usb
    from devboost.usb.probe import DiskState

    monkeypatch.setattr(cli_usb, "probe", lambda ctx, device: DiskState("blank"))
    result = runner.invoke(
        app,
        ["usb", "--device", "/dev/sdb", "--no-wizard", "--arch", "aarch64", "--dry-run", "--yes"],
    )
    assert result.exit_code == 1  # iso_for raises UsbError → caught → clean exit, not a traceback
