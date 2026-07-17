from __future__ import annotations

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.devices import list_removable, unmount_children, validate
from devboost.model import Ctx

OS = OsInfo("fedora", "fedora", "x86_64")
# lsblk -P output (one device per line, key="value" pairs)
_LSBLK = (
    'PATH="/dev/sda" SIZE="512G" TYPE="disk" RM="0" MOUNTPOINT="" MODEL="Samsung SSD 980"'
    ' VENDOR="Samsung" SERIAL="S1" TRAN="nvme"\n'
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
    'PATH="/dev/sdc" SIZE="16G" TYPE="disk" RM="1" MOUNTPOINT="/run/media/u/X" MODEL="Cruzer"'
    ' VENDOR="SanDisk" SERIAL="ABC" TRAN="usb"\n'
)


def test_list_removable_filters_to_unmounted_removable_disks() -> None:
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    devs = list_removable(ctx)
    assert [d.path for d in devs] == ["/dev/sdb"]          # sda fixed, sdc mounted -> excluded
    d = devs[0]
    assert d.size == "32G" and d.model == "Ultra" and d.vendor == "SanDisk" and d.tran == "usb"
    assert d.label() == "/dev/sdb  —  SanDisk Ultra (usb)  —  32G  [sn:4C53]"


def test_validate_rejects_fixed_and_mounted() -> None:
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    with pytest.raises(DeviceError):
        validate(ctx, "/dev/sda")          # RM=0 -> rejected
    with pytest.raises(DeviceError):
        validate(ctx, "/dev/sdc")          # mounted -> rejected
    validate(ctx, "/dev/sdb")              # removable, unmounted -> OK (no raise)


def test_validate_rejects_when_child_partition_is_mounted() -> None:
    """A whole-disk lsblk -d can show the disk as unmounted even when a partition is mounted.

    The new child-partition check must catch this case and reject the device.
    """
    # Combined output: disk is TYPE=disk/unmounted but sdb1 has a MOUNTPOINT
    _LSBLK_WITH_MOUNTED_CHILD = (
        'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
        ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
        # The following line is returned by the child-check lsblk call:
        'NAME="sdb" MOUNTPOINT=""\n'
        'NAME="sdb1" MOUNTPOINT="/run/media/user/VTOY"\n'
    )
    ctx = Ctx(
        os=OS,
        ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_WITH_MOUNTED_CHILD)}),
    )
    with pytest.raises(DeviceError, match="mounted"):
        validate(ctx, "/dev/sdb")


def test_validate_passes_when_child_partitions_unmounted() -> None:
    """Children with empty MOUNTPOINT must not trigger a rejection."""
    _LSBLK_CLEAN_CHILDREN = (
        'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
        ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
        'NAME="sdb" MOUNTPOINT=""\n'
        'NAME="sdb1" MOUNTPOINT=""\n'
        'NAME="sdb2" MOUNTPOINT=""\n'
    )
    ctx = Ctx(
        os=OS,
        ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_CLEAN_CHILDREN)}),
    )
    # Should not raise
    validate(ctx, "/dev/sdb")


# --- unmount_children: clearing GNOME/udisks2 auto-mounts off a confirmed target ----------

# The real-world case: plugging any USB with a filesystem into GNOME makes udisks2 mount it
# at /run/media/<user>/<LABEL>, so the disk reads as unmounted while a child is mounted.
_LSBLK_AUTOMOUNTED = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
    'NAME="sdb" MOUNTPOINT=""\n'
    'NAME="sdb1" MOUNTPOINT="/run/media/dev/FEDORA-WS-L"\n'
)

# The same stick once the auto-mount is cleared.
_LSBLK_UNMOUNTED = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
    'NAME="sdb" MOUNTPOINT=""\n'
    'NAME="sdb1" MOUNTPOINT=""\n'
)


def test_unmount_children_clears_an_automounted_partition() -> None:
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_AUTOMOUNTED)})
    unmount_children(Ctx(os=OS, ex=ex), "/dev/sdb")
    assert ["sudo", "umount", "/dev/sdb1"] in ex.calls
    # Having unmounted it, the device must now pass the gate that previously refused it.
    clean = FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_UNMOUNTED)})
    validate(Ctx(os=OS, ex=clean), "/dev/sdb")


def test_unmount_children_touches_nothing_when_no_child_is_mounted() -> None:
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_UNMOUNTED)})
    unmount_children(Ctx(os=OS, ex=ex), "/dev/sdb")
    assert not [c for c in ex.calls if "umount" in c]


def test_unmount_children_never_unmounts_the_disk_itself() -> None:
    """The disk node shares the lsblk output; only child partitions may be unmounted."""
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_AUTOMOUNTED)})
    unmount_children(Ctx(os=OS, ex=ex), "/dev/sdb")
    unmounted = [c[-1] for c in ex.calls if "umount" in c]
    assert unmounted == ["/dev/sdb1"]  # never /dev/sdb


def test_unmount_children_raises_when_umount_fails() -> None:
    """A busy partition must fail loudly -- never silently proceed to wipe a mounted disk."""
    ex = FakeExecutor(
        scripts={"lsblk": Result(0, stdout=_LSBLK_AUTOMOUNTED), "umount": Result(1)}
    )
    with pytest.raises(DeviceError, match="could not unmount"):
        unmount_children(Ctx(os=OS, ex=ex), "/dev/sdb")
