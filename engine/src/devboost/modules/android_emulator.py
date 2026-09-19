"""android-emulator — the Android emulator + one Pixel AVD (opt-in, every OS; spec §2)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.dev_stacks import AndroidSdk

API = 35  # matches android-sdk's platforms;android-35
AVD = "devboost-pixel"
DEVICE = "pixel_8"


def _abi(os_info: OsInfo) -> str:
    return "arm64-v8a" if os_info.arch == "aarch64" else "x86_64"


def system_image(os_info: OsInfo) -> str:
    return f"system-images;android-{API};google_apis;{_abi(os_info)}"


def sdk_root(os_info: OsInfo) -> Path:
    if env := os.environ.get("ANDROID_HOME"):
        return Path(env)
    home = Path(os.environ["HOME"])
    if os_info.family == "macos":
        return home / "Library" / "Android" / "sdk"
    return home / "Android" / "Sdk"


def avd_ini() -> Path:
    base = os.environ.get("ANDROID_AVD_HOME") or str(Path(os.environ["HOME"]) / ".android" / "avd")
    return Path(base) / f"{AVD}.ini"


def _tool(root: Path, name: str) -> str:
    """The SDK's own cmdline-tools copy if present, else PATH (brew's android-commandlinetools)."""
    local = root / "cmdline-tools" / "latest" / "bin" / name
    return str(local) if local.exists() else name


@register
class AndroidEmulator(Module):
    name = "android-emulator"
    category = "react-native"
    description = "Android emulator + a Pixel AVD (API 35; arm64-v8a on Apple Silicon)."
    requires = (AndroidSdk,)
    gui = True
    portable = True

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        # Google ships no Linux arm64 emulator host.
        return not (os_info.family != "macos" and os_info.arch == "aarch64")

    def verify(self, ctx: Ctx) -> bool:
        root = sdk_root(ctx.os)
        image = root / "system-images" / f"android-{API}" / "google_apis" / _abi(ctx.os)
        return (root / "emulator" / "emulator").exists() and image.is_dir() and avd_ini().exists()

    def install(self, ctx: Ctx) -> None:
        root = sdk_root(ctx.os)
        env = {"ANDROID_HOME": str(root), "ANDROID_SDK_ROOT": str(root)}
        image = system_image(ctx.os)
        sdkmanager = _tool(root, "sdkmanager")
        script = (
            f"yes | {shlex.quote(sdkmanager)} --sdk_root={shlex.quote(str(root))} "
            f"emulator {shlex.quote(image)}"
        )
        res = ctx.ex.run(["sh", "-c", script], env=env)
        if not res.ok:
            raise InstallError("android-emulator", f"sdkmanager emulator {image}", res.code)
        if avd_ini().exists():
            return
        argv = [_tool(root, "avdmanager"), "create", "avd", "-n", AVD, "-k", image, "-d", DEVICE]
        made = ctx.ex.run(argv, stdin="no\n", env=env)  # "no" = no custom hardware profile
        if not made.ok:
            raise InstallError("android-emulator", " ".join(argv), made.code)
