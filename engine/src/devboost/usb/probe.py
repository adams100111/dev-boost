"""Read-only disk-state detection: is this stick blank, a foreign Ventoy, or dev-boost?"""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal

from devboost.core import log
from devboost.model import Ctx
from devboost.usb.marker import Marker, read_marker

_PAIR = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class DiskState:
    kind: Literal["blank", "ventoy-other", "devboost"]
    marker: Marker | None = None


def _vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """Return the /dev path of the child partition labelled VTOY, or None."""
    out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,LABEL", device]).stdout
    for line in out.splitlines():
        fields = dict(_PAIR.findall(line))
        if fields.get("LABEL") == "VTOY":
            name = fields.get("NAME", "")
            if not name:
                return None
            return name if name.startswith("/dev/") else f"/dev/{name}"
    return None


def probe(ctx: Ctx, device: str) -> DiskState:
    """Read-only: detect a VTOY partition, ro-mount it, read the dev-boost marker.

    Never blocks: any failure degrades to DiskState("blank") with a warning.
    """
    try:
        part = _vtoy_partition(ctx, device)
        if part is None:
            return DiskState("blank")
        mnt = Path(mkdtemp(prefix="devboost-probe-"))
        try:
            if ctx.ex.run(["mount", "-o", "ro", part, str(mnt)], sudo=True).code != 0:
                log.warn(f"probe: could not mount {part} read-only; treating {device} as blank")
                return DiskState("blank")
            marker = read_marker(mnt)
            if marker is not None:
                return DiskState("devboost", marker)
            return DiskState("ventoy-other")
        finally:
            with suppress(Exception):
                ctx.ex.run(["umount", str(mnt)], sudo=True)
            with suppress(OSError):
                mnt.rmdir()
    except Exception as exc:  # a read-only probe must never block the run
        log.warn(f"probe: {device} inspection failed ({exc}); treating as blank")
        return DiskState("blank")
