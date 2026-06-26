"""Pinned Fedora ISO catalog (id -> url + sha256 + edition).

Pins are the in-repo source of truth (Principle III). Update via the Fedora release
metalink/CHECKSUM; verify the hash before committing — never invent one.
"""

from __future__ import annotations

from devboost.core.errors import UsbError
from devboost.usb.config import IsoSpec

# PLACEHOLDER — replace with the real Fedora CHECKSUM sha256 before release
FEDORA: dict[str, IsoSpec] = {
    "fedora-44": IsoSpec(
        id="fedora-44",
        url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.5.iso",
        sha256="0000000000000000000000000000000000000000000000000000000000000000",
        edition="Everything-netinst",
    ),
}

# Arch pinning: FEDORA catalog currently contains only x86_64 ISOs.
_ARCH_SUPPORT: dict[str, set[str]] = {
    "fedora-44": {"x86_64"},
}


def iso_for(iso_id: str, arch: str) -> IsoSpec:
    """Return the IsoSpec for *iso_id* on *arch*, or raise UsbError if unsupported."""
    supported = _ARCH_SUPPORT.get(iso_id, set())
    if arch not in supported:
        raise UsbError(f"no pinned Fedora ISO for arch {arch!r} (iso_id={iso_id!r})")
    return FEDORA[iso_id]


def default_iso() -> IsoSpec:
    return FEDORA["fedora-44"]
