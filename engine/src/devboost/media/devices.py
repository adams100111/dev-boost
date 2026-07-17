"""Removable-device discovery + safety guards (the single destructive target)."""

from __future__ import annotations

import os
import re

from devboost.core import log
from devboost.core.errors import DeviceError
from devboost.media.config import Device
from devboost.model import Ctx

# `lsblk -P` emits robust key="value" pairs (safe for empty/multi-word fields like MODEL).
_FIELDS = ["PATH", "SIZE", "TYPE", "RM", "MOUNTPOINT", "MODEL", "VENDOR", "SERIAL", "TRAN"]
_PAIR = re.compile(r'(\w+)="([^"]*)"')


def _parse(ctx: Ctx) -> list[Device]:
    out = ctx.ex.run(["lsblk", "-d", "-P", "-o", ",".join(_FIELDS)]).stdout
    devices: list[Device] = []
    for line in out.splitlines():
        f = dict(_PAIR.findall(line))
        if not f.get("PATH") or f.get("TYPE") != "disk":
            continue
        devices.append(Device(
            name=f["PATH"].rsplit("/", 1)[-1],
            path=f["PATH"],
            size=f.get("SIZE", ""),
            model=f.get("MODEL", "").strip(),
            removable=f.get("RM") == "1",
            mounted=bool(f.get("MOUNTPOINT", "").strip()),
            vendor=f.get("VENDOR", "").strip(),
            serial=f.get("SERIAL", "").strip(),
            tran=f.get("TRAN", "").strip(),
        ))
    return devices


def list_removable(ctx: Ctx) -> list[Device]:
    return [d for d in _parse(ctx) if d.removable and not d.mounted]


def validate(ctx: Ctx, path: str) -> None:
    match = next((d for d in _parse(ctx) if d.path == path), None)
    if match is None:
        raise DeviceError(f"{path}: not a block device")
    if not match.removable:
        raise DeviceError(f"refusing {path}: not a removable whole disk")
    if match.mounted:
        raise DeviceError(f"refusing {path}: mounted — unmount first")
    # lsblk -d only shows the disk itself, not child partitions.  A USB with a mounted
    # partition (e.g. the VTOY FAT32 filesystem) would slip past the check above.
    for part, mnt in mounted_children(ctx, path):
        raise DeviceError(f"refusing {path}: partition {part} is mounted ({mnt}) — unmount first")


#: The label Ventoy gives its *data* partition (VentoyWorker.sh: ``VTNEW_LABEL='Ventoy'`` ->
#: ``mkexfatfs -n "$VTNEW_LABEL"``).  Overridable upstream via ``-L``, which dev-boost never
#: passes.  NOT "VTOY" — that string appears nowhere on a Ventoy disk.  The ESP is labelled
#: VTOYEFI (hardcoded in ventoy_lib.sh) and is deliberately not what we look for here.
VTOY_DATA_LABEL = "Ventoy"


def owner_mount_opts() -> str:
    """``uid=,gid=`` mount options granting *this* process ownership of a FAT-family mount.

    exfat/vfat carry no on-disk ownership: the kernel assigns uid/gid at mount time from
    these options, defaulting to the mounting process — which is root, because mounting
    needs sudo.  The engine stages files with the stdlib as the invoking (unprivileged)
    user, so without this every write into the mount fails with EACCES.  Running as root
    (firstboot) yields uid=0 — the previous behaviour.
    """
    return f"uid={os.getuid()},gid={os.getgid()}"


def vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """The /dev path of *device*'s Ventoy **data** partition, or None if it has none.

    Single source of truth: probing an existing stick and verifying a fresh install must
    agree on what a Ventoy disk looks like.
    """
    out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,LABEL", device]).stdout
    for line in out.splitlines():
        f = dict(_PAIR.findall(line))
        if f.get("LABEL") == VTOY_DATA_LABEL:
            name = f.get("NAME", "")
            if not name:
                return None
            return name if name.startswith("/dev/") else f"/dev/{name}"
    return None


def mounted_children(ctx: Ctx, path: str) -> list[tuple[str, str]]:
    """``[(partition, mountpoint)]`` for every mounted child partition of *path*.

    ``lsblk -d`` reports only the disk, whose own MOUNTPOINT is empty even while a partition
    on it is mounted — so the disk-level check alone cannot see this.
    """
    disk_name = path.rsplit("/", 1)[-1]  # e.g. "sdb" from "/dev/sdb"
    out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,MOUNTPOINT", path]).stdout
    found: list[tuple[str, str]] = []
    for line in out.splitlines():
        f = dict(_PAIR.findall(line))
        name = f.get("NAME", "")
        mnt = f.get("MOUNTPOINT", "").strip()
        if name and name != disk_name and mnt:
            found.append((name if name.startswith("/dev/") else f"/dev/{name}", mnt))
    return found


def unmount_children(ctx: Ctx, path: str) -> None:
    """Unmount every mounted child partition of *path*.

    Plugging in any USB carrying a filesystem makes udisks2 (GNOME) mount it under
    /run/media/<user>/<LABEL> immediately, which would otherwise make ``validate`` refuse the
    very device the user just confirmed — on essentially every run.

    ONLY children of *path* are ever touched, and callers must confirm the wipe first: this
    unmounts strictly less than the destruction the user has already authorised for *path*.
    """
    for part, mnt in mounted_children(ctx, path):
        log.info(f"unmounting {part} ({mnt})")
        if ctx.ex.run(["umount", part], sudo=True).code != 0:
            raise DeviceError(
                f"could not unmount {part} ({mnt}) — close anything using it and retry"
            )
