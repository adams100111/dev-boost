from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.media.builder import build
from devboost.media.cache import Cache
from devboost.media.config import IsoSpec, MediaConfig
from devboost.media.download import FakeDownloader
from devboost.media.report import FakeReporter
from devboost.model import Ctx


def test_build_runs_boot_then_extras(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.media.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = MediaConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path)
    build(
        Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
        cfg,
        FakeDownloader(Cache(tmp_path), {}),
        vtoy_mount=tmp_path / "VTOY",
        reporter=FakeReporter(),
    )
    assert order == ["boot", "extra", "installers"]


def test_build_calls_mirror_when_offline_mirror_true(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.media.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))
    monkeypatch.setattr(stages, "mirror", lambda *a, **k: order.append("mirror"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = MediaConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, offline_mirror=True
    )
    build(
        Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
        cfg,
        FakeDownloader(Cache(tmp_path), {}),
        vtoy_mount=tmp_path / "VTOY",
        reporter=FakeReporter(),
    )
    assert order == ["boot", "extra", "installers", "mirror"]


def test_build_no_mirror_when_offline_mirror_false(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.media.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))

    data = b"iso"
    iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = MediaConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, offline_mirror=False
    )
    build(
        Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
        cfg,
        FakeDownloader(Cache(tmp_path), {}),
        vtoy_mount=tmp_path / "VTOY",
        reporter=FakeReporter(),
    )
    assert order == ["boot", "extra", "installers"]
    assert "mirror" not in order


def test_build_update_mode_calls_update_stage_not_boot(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.media.stages as stages
    from devboost.media.report import FakeReporter

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "update_stage", lambda *a, **k: order.append("update"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: None)
    monkeypatch.setattr(stages, "installers", lambda *a, **k: None)

    iso = IsoSpec("fedora-44", "u", hashlib.sha256(b"i").hexdigest(), "E")
    cfg = MediaConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, mode="update"
    )
    build(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
          cfg, FakeDownloader(Cache(tmp_path), {}), vtoy_mount=tmp_path / "VTOY",
          reporter=FakeReporter())
    assert order == ["update"] and "boot" not in order
