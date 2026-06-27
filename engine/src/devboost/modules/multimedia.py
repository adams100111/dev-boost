"""multimedia profile — full ffmpeg, codecs, VA-API (GPU-aware), OpenH264.

Fedora path: RPM Fusion swap (ffmpeg-full, codecs, openh264-fedora).
Ubuntu path: apt equivalents (ffmpeg-ubuntu, codecs-ubuntu).
VA-API (va-hwaccel): cross-distro with OS-aware package selection.
"""

from __future__ import annotations

from typing import ClassVar

from devboost.core import log
from devboost.core.errors import UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules.base import Rpmfusion


@register
class FfmpegFull(Module):
    name = "ffmpeg-full"
    category = "multimedia"
    description = "Swap ffmpeg-free for the full ffmpeg from RPM Fusion (Fedora-only)."
    requires = (Rpmfusion,)
    profiles = ("multimedia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "ffmpeg"]).ok and not ctx.ex.run(
            ["rpm", "-q", "ffmpeg-free"]
        ).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"ffmpeg-full requires RPM Fusion (Fedora-only); detected {ctx.os.distro!r}"
            )
        ctx.ex.run(["dnf", "swap", "ffmpeg-free", "ffmpeg", "--allowerasing", "-y"], sudo=True)


@register
class FfmpegUbuntu(Module):
    """ffmpeg from Ubuntu universe.

    Ubuntu ships a patent-unencumbered ffmpeg build in the *universe* pocket
    (enabled by default on Ubuntu desktop).  This is the Ubuntu equivalent of
    the Fedora ``ffmpeg-full`` module.
    """

    name = "ffmpeg-ubuntu"
    category = "multimedia"
    description = "ffmpeg from Ubuntu universe (Ubuntu/Debian-only)."
    profiles = ("multimedia",)
    families: ClassVar[tuple[str, ...]] = ("debian",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("ffmpeg")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "debian":
            raise UnsupportedOS(
                f"ffmpeg-ubuntu is Ubuntu/Debian-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "ffmpeg")


@register
class Codecs(Module):
    name = "codecs"
    category = "multimedia"
    description = "Install the @multimedia codec group (Fedora-only via RPM Fusion)."
    requires = (Rpmfusion,)
    profiles = ("multimedia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "gstreamer1-plugins-bad-freeworld"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"codecs (@multimedia group) is Fedora-only; detected {ctx.os.distro!r}"
            )
        ctx.ex.run(
            ["dnf", "update", "@multimedia", "--setopt=install_weak_deps=False",
             "--exclude=PackageKit-gstreamer-plugin", "-y"],
            sudo=True,
        )


@register
class CodecsUbuntu(Module):
    """Restricted codec bundle for Ubuntu/Debian.

    ``ubuntu-restricted-extras`` pulls in MP3, AAC, H.264 playback support
    and common fonts.  ``libavcodec-extra`` adds the full FFmpeg codec set
    (including patented codecs accepted under Ubuntu's restricted licence).
    This is the Ubuntu equivalent of the Fedora ``codecs`` module.
    """

    name = "codecs-ubuntu"
    category = "multimedia"
    description = "ubuntu-restricted-extras + libavcodec-extra (Ubuntu-only)."
    profiles = ("multimedia",)
    families: ClassVar[tuple[str, ...]] = ("debian",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "debian":
            return False
        return pkg.installed(ctx, "ubuntu-restricted-extras")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "debian":
            raise UnsupportedOS(
                f"codecs-ubuntu is Ubuntu/Debian-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "ubuntu-restricted-extras", "libavcodec-extra")


@register
class VaHwaccel(Module):
    name = "va-hwaccel"
    category = "multimedia"
    description = "GPU-aware VA-API hardware acceleration (Intel/AMD/NVIDIA); cross-distro."
    # Rpmfusion is NOT in requires to keep this module cross-distro.  On Fedora the AMD
    # freeworld swap works because the multimedia profile already installs ffmpeg-full
    # (which requires Rpmfusion) earlier in the run.  Standalone installs on Fedora with
    # AMD GPU must ensure Rpmfusion is enabled first.
    profiles = ("multimedia",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["vainfo"]).ok

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "libva-utils")
        gpu_out = ctx.ex.run(["lspci"]).stdout
        controllers = [
            ln for ln in gpu_out.splitlines()
            if any(k in ln for k in ("VGA compatible controller", "3D controller",
                                     "Display controller"))
        ]
        has_intel = any("Intel" in ln for ln in controllers)
        has_amd = any("AMD" in ln or "ATI" in ln for ln in controllers)
        has_nvidia = any("NVIDIA" in ln for ln in controllers)
        if not (has_intel or has_amd or has_nvidia):
            raise UnsupportedOS("va-hwaccel: no recognized GPU vendor for VA-API driver")

        if ctx.os.family == "fedora":
            if has_intel:
                pkg.install(ctx, "intel-media-driver")
            if has_amd:
                ctx.ex.run(
                    ["dnf", "swap", "-y", "mesa-va-drivers", "mesa-va-drivers-freeworld"],
                    sudo=True,
                )
                ctx.ex.run(
                    ["dnf", "swap", "-y", "mesa-vdpau-drivers", "mesa-vdpau-drivers-freeworld"],
                    sudo=True,
                )
            if has_nvidia:
                pkg.install(ctx, "libva-nvidia-driver")
        elif ctx.os.family == "debian":
            # Ubuntu universe already ships the open-source Mesa VA drivers; no swap needed.
            # intel-media-va-driver covers Intel Gen 8+ (Broadwell+).
            if has_intel:
                pkg.install(ctx, "intel-media-va-driver")
            if has_amd:
                pkg.install(ctx, "mesa-va-drivers")
            if has_nvidia:
                # nvidia-vaapi-driver bridges the NVIDIA proprietary stack to VA-API.
                pkg.install(ctx, "nvidia-vaapi-driver")
        else:
            raise UnsupportedOS(
                f"va-hwaccel: unsupported OS family {ctx.os.family!r} ({ctx.os.distro!r})"
            )

        log.ok("va-hwaccel: VA-API driver(s) installed")


@register
class Openh264(Module):
    name = "openh264"
    category = "multimedia"
    description = "Cisco OpenH264 for browser H.264 support (Fedora-only)."
    profiles = ("multimedia",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)
    _PKGS = ("openh264", "gstreamer1-plugin-openh264", "mozilla-openh264")

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", *self._PKGS]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"openh264 (Cisco repo + mozilla plugin) is Fedora-only; detected {ctx.os.distro!r}"
            )
        ctx.ex.run(["dnf", "config-manager", "setopt", "fedora-cisco-openh264.enabled=1"],
                   sudo=True)
        pkg.install(ctx, *self._PKGS)
