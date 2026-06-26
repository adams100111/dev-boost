"""Pinned Fedora ISO catalog (id -> url + sha256 + edition).

Pins are the in-repo source of truth (Principle III). Update via the Fedora release
metalink/CHECKSUM; verify the hash before committing — never invent one.
"""

from __future__ import annotations

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


def default_iso() -> IsoSpec:
    return FEDORA["fedora-44"]
