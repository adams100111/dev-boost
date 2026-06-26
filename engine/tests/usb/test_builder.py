from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.config import IsoSpec, UsbBuildConfig
from devboost.usb.download import FakeDownloader


def test_build_runs_boot_then_extras(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.usb.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = UsbBuildConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path)
    build(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
          cfg, FakeDownloader(Cache(tmp_path), {}), vtoy_mount=tmp_path / "VTOY")
    assert order == ["boot", "extra", "installers"]


def test_build_calls_mirror_when_offline_mirror_true(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.usb.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))
    monkeypatch.setattr(stages, "mirror", lambda *a, **k: order.append("mirror"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, offline_mirror=True
    )
    build(
        Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
        cfg,
        FakeDownloader(Cache(tmp_path), {}),
        vtoy_mount=tmp_path / "VTOY",
    )
    assert order == ["boot", "extra", "installers", "mirror"]


def test_build_no_mirror_when_offline_mirror_false(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.usb.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, offline_mirror=False
    )
    build(
        Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
        cfg,
        FakeDownloader(Cache(tmp_path), {}),
        vtoy_mount=tmp_path / "VTOY",
    )
    assert order == ["boot", "extra", "installers"]
    assert "mirror" not in order
