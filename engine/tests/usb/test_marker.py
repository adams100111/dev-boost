from __future__ import annotations

from pathlib import Path

from devboost.usb.marker import Marker, marker_path, read_marker, write_marker


def _m() -> Marker:
    return Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                  built_at="2026-06-26T00:00:00+00:00")


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    vtoy = tmp_path / "VTOY"
    p = write_marker(vtoy, _m())
    assert p == marker_path(vtoy)
    got = read_marker(vtoy)
    assert got == _m()


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_marker(tmp_path) is None


def test_read_invalid_json_returns_none(tmp_path: Path) -> None:
    p = marker_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert read_marker(tmp_path) is None
