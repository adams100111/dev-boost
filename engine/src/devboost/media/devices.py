"""Removable-device discovery + safety guards (the single destructive target)."""

from __future__ import annotations

import re

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
    # partition (e.g. the VTOY FAT32 filesystem) would slip past the check above.  Run a
    # second lsblk without -d and reject any child with a non-empty mountpoint.
    disk_name = path.rsplit("/", 1)[-1]  # e.g. "sdb" from "/dev/sdb"
    child_out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,MOUNTPOINT", path]).stdout
    for line in child_out.splitlines():
        f = dict(_PAIR.findall(line))
        name = f.get("NAME", "")
        mnt = f.get("MOUNTPOINT", "").strip()
        if name and name != disk_name and mnt:
            raise DeviceError(
                f"refusing {path}: partition /dev/{name} is mounted ({mnt}) — unmount first"
            )
