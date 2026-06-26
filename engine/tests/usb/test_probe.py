from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.usb.marker import Marker, write_marker
from devboost.usb.probe import probe

OS = OsInfo("fedora", "fedora", "x86_64")
_VTOY = 'NAME="sdb1" LABEL="VTOY"\nNAME="sdb2" LABEL="boot"\n'
_NO_VTOY = 'NAME="sdb1" LABEL="data"\n'


def _ctx(lsblk: str, mount_code: int = 0) -> Ctx:
    return Ctx(os=OS, ex=FakeExecutor(
        scripts={"lsblk": Result(0, stdout=lsblk), "mount": Result(mount_code)}
    ))


def test_probe_devboost_when_marker_present(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    write_marker(mnt, Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                             built_at="2026-06-26T00:00:00+00:00"))
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "devboost"
    assert state.marker is not None and state.marker.os_id == "fedora-44"


def test_probe_ventoy_other_when_vtoy_without_marker(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "ventoy-other" and state.marker is None


def test_probe_blank_when_no_vtoy_partition() -> None:
    ctx = _ctx(_NO_VTOY)
    state = probe(ctx, "/dev/sdb")
    assert state.kind == "blank"
    # never mounts when there is no VTOY partition
    assert not any("mount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_probe_blank_when_mount_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(tmp_path / "mnt"))
    (tmp_path / "mnt").mkdir()
    state = probe(_ctx(_VTOY, mount_code=1), "/dev/sdb")
    assert state.kind == "blank"


def test_probe_always_unmounts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    ctx = _ctx(_VTOY)
    probe(ctx, "/dev/sdb")
    assert any("umount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
