from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.passstore.layout import DeviceRecord, RotationEntry, Store, now_iso

FP = "A" * 40


def _store(tmp_path: Path) -> Store:
    (tmp_path / ".git").mkdir()
    return Store(tmp_path)


def test_gpg_ids_root_and_folder(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert s.gpg_ids() == []
    (tmp_path / ".gpg-id").write_text(f"{FP}\n\n  0xBEEF0000BEEF0000 \n", encoding="utf-8")
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / ".gpg-id").write_text("X\n", encoding="utf-8")
    assert s.gpg_ids() == [FP, "0xBEEF0000BEEF0000"]
    assert s.gpg_ids("harness") == ["X"]
    assert s.is_clone()


def test_record_roundtrip_and_move(tmp_path: Path) -> None:
    s = _store(tmp_path)
    rec = DeviceRecord(name="lap", fingerprint=FP, os="fedora", requested_at=now_iso())
    s.write_record("pending", rec, "ARMORED\n")
    assert s.record("pending", "lap") == rec
    assert s.key_path("pending", "lap").read_text(encoding="utf-8") == "ARMORED\n"
    data = json.loads(s.record_path("pending", "lap").read_text(encoding="utf-8"))
    assert data["scope"] is None and data["fingerprint"] == FP
    s.move("pending", "devices", "lap")
    assert s.record("pending", "lap") is None
    assert [r.name for r in s.records("devices")] == ["lap"]
    assert s.key_path("devices", "lap").exists()


def test_records_skip_invalid_json(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = tmp_path / ".devboost" / "devices"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{", encoding="utf-8")
    assert s.records("devices") == []


def test_rotation_roundtrip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert s.rotation() == []
    e = RotationEntry(device="old", fingerprint=FP, revoked_at=now_iso(), after="abc",
                      entries=["web/github"])
    s.write_rotation([e])
    assert s.rotation() == [e]


def test_entries_exclude_meta_and_git(tmp_path: Path) -> None:
    s = _store(tmp_path)
    for rel in ("web/github.gpg", "clickup/api-token.gpg", ".git/x.gpg",
                ".devboost/devices/y.gpg", "harness/tg.gpg"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    assert s.entries() == ["clickup/api-token", "harness/tg", "web/github"]
    assert s.entries("harness") == ["harness/tg"]


@pytest.mark.parametrize("body", ["{not json", '[{"device": "lap"}]', '{"a": 1}'])
def test_malformed_rotation_raises_config_error(tmp_path: Path, body: str) -> None:
    s = _store(tmp_path)
    s.meta.mkdir()
    (s.meta / "rotation.json").write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match="rotation.json"):
        s.rotation()


def test_malformed_record_is_skipped_with_a_warning(tmp_path: Path) -> None:
    s = _store(tmp_path)
    (s.meta / "devices").mkdir(parents=True)
    (s.meta / "devices" / "bad.json").write_bytes(b"\xff{")
    s.write_record("devices", DeviceRecord(name="ok", fingerprint=FP, os="fedora"), "K")
    assert [r.name for r in s.records("devices")] == ["ok"]
