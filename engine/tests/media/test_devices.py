from __future__ import annotations

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.devices import list_removable, validate
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
