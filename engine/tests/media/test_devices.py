from __future__ import annotations

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.devices import (
    list_removable,
    unmount_children,
    validate,
    vtoy_partition,
)
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


# --- Ventoy data-partition discovery ------------------------------------------------------

# Verbatim `lsblk -P -o NAME,LABEL /dev/sdb` from a real SanDisk stick immediately after
# Ventoy 1.1.16 reported "Install Ventoy to /dev/sdb successfully finished". Grounded in an
# observed disk on purpose: the code (and its tests) previously agreed on a label — "VTOY" —
# that Ventoy never writes, so they passed while the real thing could never work.
_LSBLK_REAL_AFTER_VENTOY_INSTALL = (
    'NAME="sdb" LABEL=""\n'
    'NAME="sdb1" LABEL="Ventoy"\n'
    'NAME="sdb2" LABEL="VTOYEFI"\n'
)


def test_vtoy_partition_finds_the_data_partition_ventoy_actually_creates() -> None:
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK_REAL_AFTER_VENTOY_INSTALL)})
    # sdb1 (LABEL="Ventoy"), never sdb2 — VTOYEFI is the 32MB ESP, not the data partition.
    assert vtoy_partition(Ctx(os=OS, ex=ex), "/dev/sdb") == "/dev/sdb1"


def test_vtoy_partition_returns_none_on_a_non_ventoy_disk() -> None:
    """The stick as it arrives: a Fedora live image, no Ventoy anywhere."""
    live_usb = 'NAME="sdb" LABEL=""\nNAME="sdb1" LABEL="FEDORA-WS-L"\n'
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=live_usb)})
    assert vtoy_partition(Ctx(os=OS, ex=ex), "/dev/sdb") is None


def test_vtoy_partition_does_not_match_the_efi_partition_alone() -> None:
    """VTOYEFI is not the data partition; matching it would mount the 32MB ESP and stage
    ISOs into it."""
    ex = FakeExecutor(
        scripts={"lsblk": Result(0, stdout='NAME="sdb" LABEL=""\nNAME="sdb2" LABEL="VTOYEFI"\n')}
    )
    assert vtoy_partition(Ctx(os=OS, ex=ex), "/dev/sdb") is None
