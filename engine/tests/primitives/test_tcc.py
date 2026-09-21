"""The record of macOS privacy grants, and why it has to be verifiable.

`devboost permissions` once reported "all granted" while an app's Microphone switch
was off. The record only ever said what the user had been *asked*, under a single
blanket prompt per module, and nothing ever expired it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.exec.primitives import tcc
from devboost.model import TccGrant

GRANTS = (TccGrant("Accessibility", "AeroSpace"), TccGrant("ListenEvent", "Voxtype"))


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    # Hermetic by default: no test reads this machine's real /Applications, so the
    # real signature() is exercised and simply finds nothing.
    monkeypatch.setattr(tcc, "app_bundle", lambda app: None)
    return tmp_path


def _signatures(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str | None]) -> None:
    monkeypatch.setattr(tcc, "signature", lambda app: mapping.get(app))


# --- deep links ---------------------------------------------------------------------

def test_settings_url_and_label() -> None:
    assert tcc.settings_url("ListenEvent") == (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    )
    assert tcc.label("ListenEvent") == "Input Monitoring"
    assert tcc.label("ScreenCapture") == "Screen Recording"


def test_fix_hint_names_app_setting_and_url() -> None:
    hint = tcc.fix_hint(GRANTS[:1])
    assert "AeroSpace" in hint and "Accessibility" in hint
    assert "Privacy_Accessibility" in hint


# --- reading the signature ------------------------------------------------------------

def test_signature_is_read_from_codesigns_stderr(monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    """codesign writes its description to stderr, not stdout."""
    bundle = tmp_path / "Thing.app"
    bundle.mkdir()
    monkeypatch.setattr(tcc, "app_bundle", lambda app: bundle)

    class _P:
        returncode = 0
        stdout = ""
        stderr = (
            "Identifier=io.example\n"
            "CodeDirectory v=20400 flags=0x2(adhoc)\n"
            "CandidateCDHash sha256=abc123\n"
        )

    monkeypatch.setattr("devboost.exec.primitives.tcc.subprocess.run",
                        lambda *a, **k: _P())
    assert tcc.signature("Thing") == "sha256=abc123"


def test_signature_is_none_when_the_app_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tcc, "app_bundle", lambda app: None)
    assert tcc.signature("Nope") is None


def test_signature_is_none_when_codesign_cannot_run(monkeypatch: pytest.MonkeyPatch,
                                                    tmp_path: Path) -> None:
    monkeypatch.setattr(tcc, "app_bundle", lambda app: tmp_path)

    def _boom(*a: object, **k: object) -> None:
        raise OSError("no codesign")

    monkeypatch.setattr("devboost.exec.primitives.tcc.subprocess.run", _boom)
    assert tcc.signature("Thing") is None


# --- what counts as pending -----------------------------------------------------------

def test_pending_until_confirmed(state: Path) -> None:
    assert tcc.pending("aerospace", GRANTS) == list(GRANTS)
    tcc.confirm("aerospace", GRANTS[:1])
    assert tcc.pending("aerospace", GRANTS) == [GRANTS[1]]
    assert tcc.state_file() == state / "devboost" / "tcc.json"


def test_confirm_records_the_signature_it_saw(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch, {"AeroSpace": "sha256=one"})
    tcc.confirm("aerospace", GRANTS[:1])
    saved = json.loads(tcc.state_file().read_text(encoding="utf-8"))
    assert saved["aerospace:Accessibility:AeroSpace"] == "sha256=one"


def test_a_resigned_app_is_pending_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """TCC binds a grant to the code signature. A rebuilt bundle is a different app to
    macOS, so the grant stops applying — the record must not outlive it."""
    _signatures(monkeypatch, {"AeroSpace": "sha256=one"})
    tcc.confirm("aerospace", GRANTS[:1])
    assert tcc.pending("aerospace", GRANTS[:1]) == []

    _signatures(monkeypatch, {"AeroSpace": "sha256=two"})  # rebuilt
    assert tcc.pending("aerospace", GRANTS[:1]) == list(GRANTS[:1])


def test_an_unreadable_signature_never_re_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """No opinion is not evidence. An app we cannot read must not nag the user."""
    _signatures(monkeypatch, {"AeroSpace": "sha256=one"})
    tcc.confirm("aerospace", GRANTS[:1])
    _signatures(monkeypatch, {})  # uninstalled, unsigned, or no codesign
    assert tcc.pending("aerospace", GRANTS[:1]) == []


# --- the record written before signatures existed --------------------------------------

def _legacy(keys: list[str]) -> None:
    path = tcc.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys), encoding="utf-8")


def test_a_legacy_record_is_still_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    _legacy(["aerospace:Accessibility:AeroSpace"])
    _signatures(monkeypatch, {})
    assert tcc.pending("aerospace", GRANTS[:1]) == []


def test_a_legacy_record_is_re_established_once_the_app_can_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Those entries were recorded under the old blanket prompt, so they vouch for
    nothing. Where the app can be read, ask once and get a verifiable baseline."""
    _legacy(["aerospace:Accessibility:AeroSpace"])
    _signatures(monkeypatch, {"AeroSpace": "sha256=one"})
    assert tcc.pending("aerospace", GRANTS[:1]) == list(GRANTS[:1])

    tcc.confirm("aerospace", GRANTS[:1])
    assert tcc.pending("aerospace", GRANTS[:1]) == []


def test_a_corrupt_record_is_not_fatal() -> None:
    path = tcc.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert tcc.pending("aerospace", GRANTS) == list(GRANTS)
