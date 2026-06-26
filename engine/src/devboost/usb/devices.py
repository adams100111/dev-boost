"""Removable-device discovery + safety guards (the single destructive target)."""

from __future__ import annotations

import re

from devboost.core.errors import DeviceError
from devboost.model import Ctx
from devboost.usb.config import Device

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
