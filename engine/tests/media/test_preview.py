from __future__ import annotations

from pathlib import Path

from devboost.media.config import IsoSpec, MediaConfig
from devboost.media.marker import Marker
from devboost.media.preview import render_plan
from devboost.media.probe import DiskState

_ISO = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")


def _cfg(**kw: object) -> MediaConfig:
    base: dict[str, object] = dict(
        device="/dev/sdb", arch="x86_64", iso=_ISO, cache_dir=Path("/tmp/c")
    )
    base.update(kw)
    return MediaConfig(**base)  # type: ignore[arg-type]


def test_render_plan_blank_build() -> None:
    out = render_plan(_cfg(profiles=("full",)), DiskState("blank"), download_note="≈2.0 GB")
    assert "/dev/sdb" in out
    assert "blank" in out
    assert "build" in out
    assert "fedora-44 (x86_64)" in out
    assert "full" in out
    assert "≈2.0 GB" in out


def test_render_plan_update_shows_detected_marker_and_iso_policy() -> None:
    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    out = render_plan(_cfg(mode="update"), DiskState("devboost", marker))
    assert "dev-boost USB" in out
    assert "update" in out
    assert "payload only" in out


def test_render_plan_notes_autoinstall_media() -> None:
    out = render_plan(_cfg(autoinstall_iso=_ISO), DiskState("blank"))
    assert "Zero-touch" in out
