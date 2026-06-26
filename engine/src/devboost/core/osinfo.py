"""Host detection (OsInfo) and the per-OS resolution map (OsMap).

OsMap is the typed form of the constitution's cross-OS precedence: distro -> family -> default.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

_FAMILY = {
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora",
    "rocky": "fedora", "almalinux": "fedora",
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian", "pop": "debian",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    "macos": "macos", "darwin": "macos",
}


@dataclass(frozen=True)
class OsInfo:
    distro: str
    family: str
    arch: str
    headless: bool = False


def family_of(distro: str) -> str:
    return _FAMILY.get(distro, distro)


def is_headless(env: Mapping[str, str] | None = None) -> bool:
    e = os.environ if env is None else env
    return not (e.get("DISPLAY") or e.get("WAYLAND_DISPLAY"))


def detect(
    os_release_path: str = "/etc/os-release",
    machine: str | None = None,
    env: Mapping[str, str] | None = None,
) -> OsInfo:
    distro = "unknown"
    if platform.system() == "Darwin":
        distro = "macos"
    else:
        try:
            with open(os_release_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("ID="):
                        distro = line.split("=", 1)[1].strip().strip('"')
                        break
        except OSError:
            distro = "unknown"
    return OsInfo(
        distro=distro,
        family=family_of(distro),
        arch=machine or platform.machine(),
        headless=is_headless(env),
    )


@dataclass(frozen=True)
class OsMap(Generic[T]):
    """Per-OS values resolved distro -> family -> default."""

    fedora: T | None = None
    debian: T | None = None
    arch: T | None = None
    default: T | None = None

    def get(self, os_info: OsInfo) -> T | None:
        by_distro = {"fedora": self.fedora, "debian": self.debian, "arch": self.arch}
        if os_info.distro in by_distro and by_distro[os_info.distro] is not None:
            return by_distro[os_info.distro]
        if os_info.family in by_distro and by_distro[os_info.family] is not None:
            return by_distro[os_info.family]
        return self.default
