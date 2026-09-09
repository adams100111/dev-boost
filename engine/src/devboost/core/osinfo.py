"""Host detection (OsInfo) and the per-OS resolution map (OsMap).

OsMap is the typed form of the constitution's cross-OS precedence: distro -> family -> default.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

_FAMILY = {
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora",
    "rocky": "fedora", "almalinux": "fedora",
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian", "pop": "debian",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    "omarchy": "arch", "cachyos": "arch", "garuda": "arch",
    "macos": "macos", "darwin": "macos",
}


@dataclass(frozen=True)
class OsInfo:
    distro: str
    family: str
    arch: str
    headless: bool = False
    #: os-release VERSION_ID (e.g. "24.04") and VERSION_CODENAME (e.g. "noble").
    #: Used to build version-correct third-party repo URLs; empty when unknown.
    version_id: str = ""
    codename: str = ""
    #: os-release ID_LIKE, split into tokens (e.g. ("arch",) for Omarchy). A derivative
    #: distro that is not in _FAMILY still resolves to the right family through this.
    id_like: tuple[str, ...] = ()


def family_of(distro: str, id_like: Sequence[str] = ()) -> str:
    """Resolve a distro id to its package/tooling family.

    A known id wins outright.  Otherwise fall back through os-release ``ID_LIKE``, which is
    how a derivative distro declares its base — Omarchy ships ``ID=omarchy ID_LIKE=arch``.
    Without this step an unknown derivative resolves to a family of its own name, and every
    ``OsMap`` lookup for it silently returns ``default`` (i.e. no strategy at all) rather
    than the base distro's.  Unknown and unrelated ids still resolve to themselves.
    """
    if distro in _FAMILY:
        return _FAMILY[distro]
    for like in id_like:
        if like in _FAMILY:
            return _FAMILY[like]
    return distro


def is_headless(
    env: Mapping[str, str] | None = None,
    default_target_link: str = "/etc/systemd/system/default.target",
) -> bool:
    """Return True when the host is not a graphical machine (e.g. a server).

    An active session is conclusive: if ``DISPLAY``/``WAYLAND_DISPLAY`` is set, the host
    is graphical.  Otherwise — which includes a desktop mid-provisioning before any session
    exists — fall back to the systemd *default target*: ``graphical.target`` means the box
    boots to a GUI (not headless); anything else (``multi-user.target`` — a server) means
    headless.  This avoids the trap of treating a freshly-provisioned laptop (no ``DISPLAY``
    yet) as a server.  When the target can't be read, assume headless (skip GUI installs).
    """
    e = os.environ if env is None else env
    if e.get("DISPLAY") or e.get("WAYLAND_DISPLAY"):
        return False
    try:
        target = os.readlink(default_target_link)
    except OSError:
        return True
    return not target.endswith("graphical.target")


def detect(
    os_release_path: str = "/etc/os-release",
    machine: str | None = None,
    env: Mapping[str, str] | None = None,
    default_target_link: str = "/etc/systemd/system/default.target",
) -> OsInfo:
    distro = "unknown"
    version_id = ""
    codename = ""
    id_like: tuple[str, ...] = ()
    if platform.system() == "Darwin":
        distro = "macos"
    else:
        try:
            with open(os_release_path, encoding="utf-8") as fh:
                for line in fh:
                    key, sep, val = line.partition("=")
                    if not sep:
                        continue
                    val = val.strip().strip('"')
                    if key == "ID":
                        distro = val
                    elif key == "VERSION_ID":
                        version_id = val
                    elif key == "VERSION_CODENAME":
                        codename = val
                    elif key == "ID_LIKE":
                        # Space-separated, most-similar-first (os-release spec).
                        id_like = tuple(val.split())
        except OSError:
            distro = "unknown"
    return OsInfo(
        distro=distro,
        family=family_of(distro, id_like),
        arch=machine or platform.machine(),
        headless=is_headless(env, default_target_link),
        version_id=version_id,
        codename=codename,
        id_like=id_like,
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
