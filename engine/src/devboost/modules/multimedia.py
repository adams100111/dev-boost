"""multimedia profile — full ffmpeg, codecs, VA-API (GPU-aware), OpenH264."""

from __future__ import annotations

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
    description = "Swap ffmpeg-free for the full ffmpeg from RPM Fusion."
    requires = (Rpmfusion,)
    profiles = ("multimedia",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", "ffmpeg"]).ok and not ctx.ex.run(
            ["rpm", "-q", "ffmpeg-free"]
        ).ok

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["dnf", "swap", "ffmpeg-free", "ffmpeg", "--allowerasing", "-y"], sudo=True)


@register
class Codecs(Module):
    name = "codecs"
    category = "multimedia"
    description = "Install the @multimedia codec group."
    requires = (Rpmfusion,)
    profiles = ("multimedia",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", "gstreamer1-plugins-bad-freeworld"]).ok

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(
            ["dnf", "update", "@multimedia", "--setopt=install_weak_deps=False",
             "--exclude=PackageKit-gstreamer-plugin", "-y"],
            sudo=True,
        )


@register
class VaHwaccel(Module):
    name = "va-hwaccel"
    category = "multimedia"
    description = "GPU-aware VA-API hardware acceleration (Intel/AMD/NVIDIA)."
    requires = (Rpmfusion,)
    profiles = ("multimedia",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["vainfo"]).ok

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "libva-utils")
        gpu = ctx.ex.run(["lspci"]).stdout
        controllers = [
            ln for ln in gpu.splitlines()
            if any(k in ln for k in ("VGA compatible controller", "3D controller",
                                     "Display controller"))
        ]
        has_intel = any("Intel" in ln for ln in controllers)
        has_amd = any("AMD" in ln or "ATI" in ln for ln in controllers)
        has_nvidia = any("NVIDIA" in ln for ln in controllers)
        if not (has_intel or has_amd or has_nvidia):
            raise UnsupportedOS("va-hwaccel: no recognized GPU vendor for VA-API driver")
        if has_intel:
            pkg.install(ctx, "intel-media-driver")
        if has_amd:
            ctx.ex.run(["dnf", "swap", "-y", "mesa-va-drivers", "mesa-va-drivers-freeworld"],
                       sudo=True)
            ctx.ex.run(["dnf", "swap", "-y", "mesa-vdpau-drivers", "mesa-vdpau-drivers-freeworld"],
                       sudo=True)
        if has_nvidia:
            pkg.install(ctx, "libva-nvidia-driver")
        log.ok("va-hwaccel: VA-API driver(s) installed")


@register
class Openh264(Module):
    name = "openh264"
    category = "multimedia"
    description = "Cisco OpenH264 for browser H.264 support."
    profiles = ("multimedia",)
    _PKGS = ("openh264", "gstreamer1-plugin-openh264", "mozilla-openh264")

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", *self._PKGS]).ok

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["dnf", "config-manager", "setopt", "fedora-cisco-openh264.enabled=1"],
                   sudo=True)
        pkg.install(ctx, *self._PKGS)
