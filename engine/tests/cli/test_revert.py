from __future__ import annotations

import pytest
from typer.testing import CliRunner

from devboost.cli import revert as revert_cli
from devboost.cli.app import app
from devboost.core import osinfo
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import macos_defaults as md
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


@pytest.fixture
def mac_prefs(monkeypatch: pytest.MonkeyPatch) -> PrefsExecutor:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    monkeypatch.setattr(osinfo, "detect", lambda **_: MAC)
    monkeypatch.setattr(revert_cli, "RealExecutor", lambda: ex)
    md.apply(Ctx(os=MAC, ex=ex))
    return ex


def test_revert_one_key(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "tilesize"])
    assert res.exit_code == 0, res.output
    assert mac_prefs.prefs[(DOCK, "tilesize")] == ("integer", "64")
    assert mac_prefs.prefs[(DOCK, "autohide")] == ("boolean", "1")


def test_revert_everything(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 0, res.output
    assert mac_prefs.prefs == {(DOCK, "tilesize"): ("integer", "64")}
    assert not md.snapshot_path().exists()


def test_unknown_key_is_a_usage_error(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "nope"])
    assert res.exit_code == 2
    assert "unknown" in res.output


def test_linux_is_refused() -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 2
    assert "macOS-only" in res.output


# --- lane M5-A additions -----------------------------------------------------------------


def test_an_ambiguous_key_is_a_usage_error(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "Clicking"])
    assert res.exit_code == 2
    assert "ambiguous" in res.output


def test_a_repeat_revert_restores_nothing_and_succeeds(mac_prefs: PrefsExecutor) -> None:
    assert CliRunner().invoke(app, ["revert", "macos-defaults"]).exit_code == 0
    mac_prefs.calls.clear()
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 0, res.output
    assert "nothing recorded" in res.output
    assert not [c for c in mac_prefs.calls if c[0] == "defaults" and c[1] != "read-type"]


def test_a_corrupt_snapshot_fails_cleanly(mac_prefs: PrefsExecutor) -> None:
    md.snapshot_path().write_text("{not json", encoding="utf-8")
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 1
    assert "not a valid macos-defaults snapshot" in res.output
    assert not isinstance(res.exception, md.SnapshotError)  # reported, not a traceback


def test_a_failed_restore_exits_1_and_keeps_the_key(mac_prefs: PrefsExecutor) -> None:
    mac_prefs.rules.append((("defaults", "write", "tilesize"), Result(1)))
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "tilesize"])
    assert res.exit_code == 1
    assert "com.apple.dock:tilesize" in md.load_snapshot()


def test_linux_never_touches_the_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise AssertionError("no executor off macOS")

    monkeypatch.setattr(revert_cli, "RealExecutor", _boom)
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 2
