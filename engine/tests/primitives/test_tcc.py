from __future__ import annotations

from pathlib import Path

import pytest

from devboost.exec.primitives import tcc
from devboost.model import TccGrant

GRANTS = (TccGrant("Accessibility", "AeroSpace"), TccGrant("ListenEvent", "Voxtype"))


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


def test_settings_url_and_label() -> None:
    assert tcc.settings_url("ListenEvent") == (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    )
    assert tcc.label("ListenEvent") == "Input Monitoring"
    assert tcc.label("ScreenCapture") == "Screen Recording"


def test_pending_until_confirmed(state: Path) -> None:
    assert tcc.pending("aerospace", GRANTS) == list(GRANTS)
    tcc.confirm("aerospace", GRANTS[:1])
    assert tcc.pending("aerospace", GRANTS) == [GRANTS[1]]
    assert tcc.state_file() == state / "devboost" / "tcc.json"


def test_fix_hint_names_app_setting_and_url() -> None:
    hint = tcc.fix_hint(GRANTS[:1])
    assert "AeroSpace" in hint and "Accessibility" in hint
    assert "Privacy_Accessibility" in hint
