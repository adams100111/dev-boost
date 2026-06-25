import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass

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


def family_of(distro: str) -> str:
    return _FAMILY.get(distro, distro)


def detect(os_release_path: str = "/etc/os-release", machine: str | None = None) -> OsInfo:
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
    return OsInfo(distro=distro, family=family_of(distro), arch=machine or platform.machine())


def is_headless(env: Mapping[str, str] | None = None) -> bool:
    e = os.environ if env is None else env
    return not (e.get("DISPLAY") or e.get("WAYLAND_DISPLAY"))
