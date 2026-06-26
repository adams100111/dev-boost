"""Supported-OS catalog (id -> friendly name + per-arch pinned IsoSpec).

Pins are the in-repo source of truth (Principle III). Update via the Fedora
release CHECKSUM; verify the hash before committing — never invent one. Adding a
distro is one Os entry; it appears in the wizard select with zero code changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import UsbError
from devboost.usb.config import IsoSpec


@dataclass(frozen=True)
class Os:
    id: str
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, IsoSpec]


CATALOG: dict[str, Os] = {
    "fedora-44": Os(
        id="fedora-44",
        name="Fedora 44 — Everything (netinst)",
        distro="fedora",
        version="44",
        edition="Everything-netinst",
        isos={
            "x86_64": IsoSpec(
                id="fedora-44",
                url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.7.iso",
                sha256="bd285201494dd0ba09b54d05ac707de1401668b8512a573edb5922dcf9d7067e",
                edition="Everything-netinst",
            ),
        },
    ),
}


def supported() -> list[Os]:
    """All catalog entries, for the wizard's friendly-named select."""
    return list(CATALOG.values())


def iso_for(os_id: str, arch: str) -> IsoSpec:
    """The pinned IsoSpec for *os_id* on *arch*, or raise UsbError."""
    os_entry = CATALOG.get(os_id)
    if os_entry is None:
        raise UsbError(f"unknown OS id {os_id!r}")
    spec = os_entry.isos.get(arch)
    if spec is None:
        raise UsbError(f"no pinned ISO for arch {arch!r} (os_id={os_id!r})")
    return spec


def default_os() -> Os:
    return CATALOG["fedora-44"]


def default_iso() -> IsoSpec:
    return default_os().isos["x86_64"]
