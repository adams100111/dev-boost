"""Read-only disk-state detection: is this stick blank, a foreign Ventoy, or dev-boost?"""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal

from devboost.core import log
from devboost.media.devices import mounted_children, owner_mount_opts, vtoy_partition
from devboost.media.marker import Marker, read_marker
from devboost.model import Ctx

_PAIR = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class DiskState:
    kind: Literal["blank", "ventoy-other", "devboost"]
    marker: Marker | None = None


def _vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """Return the /dev path of *device*'s Ventoy data partition, or None."""
    return vtoy_partition(ctx, device)


def _classify(marker: Marker | None) -> DiskState:
    """A Ventoy disk carrying our marker is a dev-boost stick; otherwise it is someone else's."""
    return DiskState("devboost", marker) if marker is not None else DiskState("ventoy-other")


def probe(ctx: Ctx, device: str) -> DiskState:
    """Read-only: find the Ventoy data partition and read the dev-boost marker off it.

    Reads through an existing mount when there is one, and otherwise ro-mounts the partition
    itself. Never blocks: any failure degrades to DiskState("blank") with a warning — which
    is why the existing-mount path matters, since "blank" is what makes the wizard offer a
    WIPE instead of an update.
    """
    try:
        part = _vtoy_partition(ctx, device)
        if part is None:
            return DiskState("blank")

        # If the partition is already mounted, read through that mount instead of making our
        # own. udisks2 auto-mounts a Ventoy stick the moment it is plugged in (GNOME's
        # automount is on by default), and a second mount of the same device with different
        # options fails EBUSY — which degraded this probe to "blank", so the wizard offered a
        # WIPE for a stick it should have offered to UPDATE, destroying the ISOs it was meant
        # to keep. Unmounting instead is not an option: this runs before the user has
        # confirmed anything, and a read-only probe must not touch what it inspects.
        for candidate, mountpoint in mounted_children(ctx, device):
            if candidate == part:
                return _classify(read_marker(Path(mountpoint)))

        mnt = Path(mkdtemp(prefix="devboost-probe-"))
        try:
            opts = f"ro,{owner_mount_opts()}"  # readable by us regardless of root's umask
            if ctx.ex.run(["mount", "-o", opts, part, str(mnt)], sudo=True).code != 0:
                log.warn(f"probe: could not mount {part} read-only; treating {device} as blank")
                return DiskState("blank")
            return _classify(read_marker(mnt))
        finally:
            with suppress(Exception):
                ctx.ex.run(["umount", str(mnt)], sudo=True)
            with suppress(OSError):
                mnt.rmdir()
    except Exception as exc:  # a read-only probe must never block the run
        log.warn(f"probe: {device} inspection failed ({exc}); treating as blank")
        return DiskState("blank")
