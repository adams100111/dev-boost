"""hardware-nvidia profile — NVIDIA driver stack (applied when an NVIDIA GPU is detected).

Fedora path: akmod-nvidia + RPM Fusion (NvidiaAkmod, Cuda, LibvaNvidiaDriver,
             NvidiaContainerToolkit, SecurebootMok, NvidiaResignService).
Ubuntu path: ubuntu-drivers autoinstall (NvidiaDriverUbuntu).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import pkg, systemd
from devboost.model import Ctx, Module
from devboost.modules.base import Rpmfusion
from devboost.modules.docker import Docker


@register
class NvidiaAkmod(Module):
    name = "nvidia-akmod"
    category = "hardware-nvidia"
    description = "akmod-nvidia driver (RPM Fusion, Fedora-only)."
    requires = (Rpmfusion,)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "akmod-nvidia"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"nvidia-akmod uses akmod/RPM Fusion (Fedora-only); detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "akmod-nvidia", "xorg-x11-drv-nvidia-cuda")


@register
class Cuda(Module):
    name = "cuda"
    category = "hardware-nvidia"
    description = "CUDA toolkit (Fedora-only via RPM Fusion)."
    requires = (NvidiaAkmod,)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "xorg-x11-drv-nvidia-cuda"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"cuda (RPM Fusion variant) is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "xorg-x11-drv-nvidia-cuda")


@register
class LibvaNvidiaDriver(Module):
    name = "libva-nvidia-driver"
    category = "hardware-nvidia"
    description = "VA-API bridge for NVIDIA (Fedora-only via RPM Fusion)."
    requires = (NvidiaAkmod,)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "libva-nvidia-driver"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"libva-nvidia-driver (RPM Fusion) is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "libva-nvidia-driver")


@register
class NvidiaContainerToolkit(Module):
    name = "nvidia-container-toolkit"
    category = "hardware-nvidia"
    description = "GPU access for containers (Fedora-only via akmod deps)."
    requires = (Docker, NvidiaAkmod)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("nvidia-ctk")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"nvidia-container-toolkit (akmod-based) is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "nvidia-container-toolkit")
        ctx.ex.run(["nvidia-ctk", "runtime", "configure", "--runtime=docker"], sudo=True)


@register
class SecurebootMok(Module):
    name = "secureboot-mok"
    category = "hardware-nvidia"
    description = "Enroll a MOK so the signed NVIDIA modules load under Secure Boot (Fedora-only)."
    requires = (NvidiaAkmod,)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def _key(self) -> Path:
        return Path("/etc/pki/akmods/certs/public_key.der")

    def verify(self, ctx: Ctx) -> bool:
        # Already enrolled when mokutil reports the akmods key in the enrolled list.
        return "akmods" in ctx.ex.run(["mokutil", "--list-enrolled"]).stdout.lower()

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"secureboot-mok uses akmods PKI paths (Fedora-only); detected {ctx.os.distro!r}"
            )
        if not self._key().exists():
            log.warn("secureboot-mok: akmods signing key absent yet — re-run after akmod build")
            return
        # Enrollment is interactive at next boot (one-time MOK screen); import is non-blocking.
        ctx.ex.run(["mokutil", "--import", str(self._key())], sudo=True)


@register
class NvidiaResignService(Module):
    name = "nvidia-resign-service"
    category = "hardware-nvidia"
    description = "Re-sign NVIDIA modules after a kernel/akmod rebuild (Fedora-only)."
    requires = (SecurebootMok,)
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def _unit(self) -> Path:
        d = os.environ.get("DEVBOOST_SYSTEMD_SYSTEM_DIR", "/etc/systemd/system")
        return Path(d) / "nvidia-resign.service"

    def verify(self, ctx: Ctx) -> bool:
        return self._unit().exists()

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"nvidia-resign-service uses akmods (Fedora-only); detected {ctx.os.distro!r}"
            )
        unit = (
            "[Unit]\nDescription=devboost NVIDIA module re-sign\nAfter=akmods.service\n\n"
            "[Service]\nType=oneshot\nExecStart=/usr/sbin/akmods --force\n\n"
            "[Install]\nWantedBy=multi-user.target\n"
        )
        path = self._unit()
        if os.access(path.parent, os.W_OK):
            path.write_text(unit, encoding="utf-8")
        else:
            ctx.ex.run(["tee", str(path)], sudo=True, stdin=unit)
        systemd.enable_system_unit(ctx, "nvidia-resign.service")


@register
class NvidiaDriverUbuntu(Module):
    """Ubuntu NVIDIA driver via ubuntu-drivers autoinstall.

    This is the Ubuntu equivalent of the akmod-based Fedora stack.  It installs
    whichever proprietary NVIDIA driver ubuntu-drivers recommends (typically the
    latest tested nvidia-driver-NNN metapackage).  Secure-Boot enrollment on Ubuntu
    is handled automatically by the DKMS/shim layer; no manual MOK step is needed.
    """

    name = "nvidia-driver-ubuntu"
    category = "hardware-nvidia"
    description = "NVIDIA driver via ubuntu-drivers autoinstall (Ubuntu-only)."
    profiles = ("hardware-nvidia",)
    families: ClassVar[tuple[str, ...]] = ("debian",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("nvidia-smi")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "debian":
            raise UnsupportedOS(
                "nvidia-driver-ubuntu uses ubuntu-drivers (Ubuntu/Debian-only);"
                f" detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "ubuntu-drivers-common")
        ctx.ex.run(["ubuntu-drivers", "autoinstall"], sudo=True)
