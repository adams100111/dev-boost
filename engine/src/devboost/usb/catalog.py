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
        name="Fedora 44 — Workstation (Live)",
        distro="fedora",
        version="44",
        edition="Workstation-Live",
        isos={
            "x86_64": IsoSpec(
                id="fedora-44",
                url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Workstation/x86_64/iso/Fedora-Workstation-Live-44-1.7.x86_64.iso",
                sha256="1620295f6a00c27c3208f0c00b8ece4eab1ec69b9002152d97488bf26a426ddf",
                edition="Workstation-Live",
            ),
            "aarch64": IsoSpec(
                id="fedora-44",
                url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Workstation/aarch64/iso/Fedora-Workstation-Live-44-1.7.aarch64.iso",
                sha256="162ba3c552a2d241c7c63ec26777af0255ee1b5a135adc0be986ceed999933ef",
                edition="Workstation-Live",
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
