from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.marker import Marker, write_marker
from devboost.media.probe import probe
from devboost.model import Ctx

OS = OsInfo("fedora", "fedora", "x86_64")
_VTOY = 'NAME="sdb1" LABEL="Ventoy"\nNAME="sdb2" LABEL="boot"\n'
_NO_VTOY = 'NAME="sdb1" LABEL="data"\n'


def _ctx(lsblk: str, mount_code: int = 0) -> Ctx:
    return Ctx(os=OS, ex=FakeExecutor(
        scripts={"lsblk": Result(0, stdout=lsblk), "mount": Result(mount_code)}
    ))


def test_probe_devboost_when_marker_present(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    write_marker(mnt, Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                             built_at="2026-06-26T00:00:00+00:00"))
    monkeypatch.setattr("devboost.media.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "devboost"
    assert state.marker is not None and state.marker.os_id == "fedora-44"


def test_probe_ventoy_other_when_vtoy_without_marker(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.media.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "ventoy-other" and state.marker is None


def test_probe_blank_when_no_vtoy_partition() -> None:
    ctx = _ctx(_NO_VTOY)
    state = probe(ctx, "/dev/sdb")
    assert state.kind == "blank"
    # never mounts when there is no VTOY partition
    assert not any("mount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_probe_blank_when_mount_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("devboost.media.probe.mkdtemp", lambda **k: str(tmp_path / "mnt"))
    (tmp_path / "mnt").mkdir()
    ctx = _ctx(_VTOY, mount_code=1)
    state = probe(ctx, "/dev/sdb")
    assert state.kind == "blank"
    assert any("umount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_probe_always_unmounts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.media.probe.mkdtemp", lambda **k: str(mnt))
    ctx = _ctx(_VTOY)
    probe(ctx, "/dev/sdb")
    assert any("umount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


# lsblk reporting the stick as udisks2/GNOME leaves it the moment it is plugged in: the
# Ventoy data partition already mounted under /run/media/<user>/Ventoy.
def _automounted(mountpoint: str) -> str:
    return (
        'NAME="sdb" LABEL="" MOUNTPOINT=""\n'
        f'NAME="sdb1" LABEL="Ventoy" MOUNTPOINT="{mountpoint}"\n'
    )


def test_probe_reads_the_marker_through_an_existing_automount(tmp_path: Path) -> None:
    """A replugged dev-boost stick is already mounted by udisks2. Mounting it again with
    different options fails EBUSY, so probe degraded to "blank" — and the wizard then offered
    a WIPE instead of an update, destroying the ISOs it should have kept.

    Read through the mount that is already there: a read-only probe must not need its own.
    """
    marker = Marker(
        version="0.1.60", os_id="fedora-44", arch="x86_64", built_at="2026-07-17T00:00:00+00:00"
    )
    write_marker(tmp_path, marker)
    ex = FakeExecutor(
        scripts={
            "lsblk": Result(0, stdout=_automounted(str(tmp_path))),
            # Any mount WE attempt would lose to the existing one; make that explicit.
            "mount": Result(32, stderr="mount: /dev/sdb1 already mounted or mount point busy."),
        }
    )
    state = probe(Ctx(os=OS, ex=ex), "/dev/sdb")
    assert state.kind == "devboost"
    assert state.marker is not None and state.marker.os_id == "fedora-44"
    assert not [c for c in ex.calls if c[:2] == ["sudo", "mount"]]  # never mounted it itself
    assert not [c for c in ex.calls if "umount" in c]  # a read-only probe unmounts nothing


def test_probe_automounted_ventoy_without_a_marker_is_ventoy_other(tmp_path: Path) -> None:
    """Same path, no marker: a foreign Ventoy stick, not a blank disk."""
    ex = FakeExecutor(
        scripts={
            "lsblk": Result(0, stdout=_automounted(str(tmp_path))),
            "mount": Result(32),
        }
    )
    state = probe(Ctx(os=OS, ex=ex), "/dev/sdb")
    assert state.kind == "ventoy-other"
