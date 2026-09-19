from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli import pass_cmd
from devboost.cli.app import app
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_ME = "A" * 40
FP_NEW = "B" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"
runner = CliRunner()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "store"))
    cfg = tmp_path / "cfg" / "devboost" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('device_name = "desk"\n', encoding="utf-8")
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / ".gpg-id").write_text(FP_ME + "\n", encoding="utf-8")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    return s


def _use(monkeypatch: pytest.MonkeyPatch, *extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    ex = RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
        (("--show-keys",), Result(0, colons("pub", FP_NEW))),
        (("diff", "--cached"), Result(1)),
        (("rev-parse", "HEAD"), Result(0, "abc\n")),
    ])
    monkeypatch.setattr(pass_cmd, "_ctx", lambda: Ctx(os=FEDORA, ex=ex))
    return ex


def test_pass_subapp_is_registered() -> None:
    out = runner.invoke(app, ["pass", "--help"]).output
    for verb in ("status", "devices", "approve", "revoke", "sync", "enroll"):
        assert verb in out


def test_status_reports_enrollment(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "status"])
    assert res.exit_code == 0, res.output
    assert "desk (enrolled)" in res.output and FP_ME in res.output


def test_status_bad_device_name_exits_cleanly(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = store.root.parent / "cfg" / "devboost" / "config.toml"
    cfg.write_text('device_name = "!!!"\n', encoding="utf-8")
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "status"])
    assert res.exit_code == 1
    assert "Traceback" not in res.output
    assert "device_name" in res.output


def test_devices_lists_enrolled_and_pending(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), ARMOR)
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "devices"])
    assert "desk" in res.output and "lap" in res.output and "pending" in res.output


def test_approve_requires_typed_y(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), ARMOR)
    ex = _use(monkeypatch)
    res = runner.invoke(app, ["pass", "approve", "lap"], input="n\n")
    assert "nothing approved" in res.output and store.record("pending", "lap") is not None
    res = runner.invoke(app, ["pass", "approve", "lap"], input="y\n")
    assert res.exit_code == 0, res.output
    assert FP_NEW in res.output and "approved lap" in res.output
    assert ["pass", "init", FP_ME, FP_NEW] in ex.calls


def test_approve_error_exits_1(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "approve", "ghost"], input="y\n")
    assert res.exit_code == 1


def test_revoke_prints_rotation_checklist(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    (store.root / ".gpg-id").write_text(f"{FP_ME}\n{FP_NEW}\n", encoding="utf-8")
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    _use(monkeypatch, ((f"-S{FP_NEW}",), Result(0, "c1\n")),
         (("ls-tree",), Result(0, "web/a.gpg\n")))
    res = runner.invoke(app, ["pass", "revoke", "lap"], input="y\n")
    assert res.exit_code == 0, res.output
    assert "[ ] web/a" in res.output and "devboost doctor" in res.output


def test_sync_resolve_prints_guidance(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "sync", "--resolve"])
    assert res.exit_code == 0 and "git rebase --continue" in res.output


def test_sync_conflict_exits_1(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, (("pull",), Result(1)), (("--diff-filter=U",), Result(0, ".gpg-id\n")))
    res = runner.invoke(app, ["pass", "sync", "--quiet"])
    assert res.exit_code == 1 and "conflict" in res.output


def test_enroll_pending_prints_next_step(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    (store.root / ".gpg-id").write_text("C" * 40 + "\n", encoding="utf-8")  # not us
    store.write_record("pending", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    (store.root / ".devboost" / "devices" / "desk.json").unlink()
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "enroll"])
    assert res.exit_code == 0 and "devboost pass approve desk" in res.output


def test_status_malformed_rotation_exits_cleanly(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    (store.meta / "rotation.json").write_text("{oops", encoding="utf-8")
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "status"])
    assert res.exit_code == 1 and "Traceback" not in res.output
    assert "rotation.json" in res.output


def test_status_invalid_config_exits_cleanly(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = store.root.parent / "cfg" / "devboost" / "config.toml"
    cfg.write_text("pass_repo = [\n", encoding="utf-8")
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "status"])
    assert res.exit_code == 1 and "invalid TOML" in res.output


def test_revoke_malformed_rotation_exits_cleanly(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    (store.root / ".gpg-id").write_text(f"{FP_ME}\n{FP_NEW}\n", encoding="utf-8")
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    (store.meta / "rotation.json").write_text("[1]", encoding="utf-8")
    ex = _use(monkeypatch)
    res = runner.invoke(app, ["pass", "revoke", "lap"], input="y\n")
    assert res.exit_code == 1 and "rotation.json" in res.output
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)
