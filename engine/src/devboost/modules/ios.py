"""ios — Xcode and the iOS simulator runtime via xcodes (opt-in `ios` profile, spec §2).

xcodes may prompt for an Apple ID password or a 2FA code, so it always runs attached to
the terminal (never with captured output, where it would block on an invisible prompt).
With neither XCODES_USERNAME/XCODES_PASSWORD nor a terminal, the module reports what the
user must do (`blocked`) instead. The credentials reach xcodes only through the inherited
environment: dev-boost never reads them into argv, an `env=` override, a log or an error.
xcodes itself then keeps the password in the login keychain for later runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.media.catalog import xcode_pin
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewFormula
from devboost.modules._credentials import is_interactive
from devboost.modules.macos import Homebrew

_IOS = ("ios",)
_MACOS = ("macos",)
_FIX = (
    "export XCODES_USERNAME and XCODES_PASSWORD, or run `devboost install ios` in a terminal"
)


def _interactive() -> bool:
    """True when a human can answer xcodes' Apple ID / 2FA prompts (patched in tests)."""
    return is_interactive()


def _require_auth(what: str) -> None:
    creds = os.environ.get("XCODES_USERNAME") and os.environ.get("XCODES_PASSWORD")
    if not (creds or _interactive()):
        raise NeedsUser(f"{what} needs an Apple ID sign-in", _FIX)


def _run_xcodes(ctx: Ctx, module: str, argv: list[str]) -> None:
    res = ctx.ex.run(argv, interactive=True)
    if res.ok:
        return
    if not _interactive():
        # Unattended: a 2FA code prompt read EOF (or the stored session expired). Only
        # the user can finish that login, so this is `blocked`, not a failure.
        raise NeedsUser(
            f"`{' '.join(argv[:3])}` exited {res.code} with no terminal — the Apple ID "
            "sign-in may need a 2FA code",
            "run `devboost install ios` in a terminal and complete the Apple ID login",
        )
    raise InstallError(module, " ".join(argv), res.code)


def _supported(os_info: OsInfo) -> bool:
    v = macos_version(os_info)
    return v is None or v >= xcode_pin().min_macos


@register
class Xcodes(Module):
    """M5-D3: no `xcodes` module existed before M5, so it lives next to its only user."""

    name = "xcodes"
    category = "ios"
    description = "xcodes — install and switch Xcode versions (MIT)."
    families: ClassVar[tuple[str, ...]] = _MACOS
    requires = (Homebrew,)
    per_os: ClassVar[OsMap[Installer]] = OsMap(macos=BrewFormula("xcodes"))


def _is_pin(line: str, version: str) -> bool:
    """`27.0 (27A266a) (Selected)\t/Applications/…` names *version*; a beta does not."""
    return line.split(" (", 1)[0].strip() == version


@dataclass(frozen=True)
class _XcodeInstall:
    def verify(self, ctx: Ctx) -> bool:
        pin = xcode_pin()
        res = ctx.ex.run(["xcodes", "installed"])
        selected = res.ok and any(
            _is_pin(line, pin.version) and "(Selected)" in line
            for line in res.stdout.splitlines()
        )
        return selected and ctx.ex.run(["xcodebuild", "-license", "check"]).ok

    def install(self, ctx: Ctx) -> None:
        pin = xcode_pin()
        _require_auth("Downloading Xcode")
        _run_xcodes(ctx, "xcode", [
            "xcodes", "install", pin.version, "--select", "--experimental-unxip",
            "--empty-trash",
        ])
        for step in (["xcodebuild", "-license", "accept"], ["xcodebuild", "-runFirstLaunch"]):
            done = ctx.ex.run(step, sudo=True)
            if not done.ok:
                raise InstallError("xcode", "sudo " + " ".join(step), done.code)


@register
class Xcode(Module):
    name = "xcode"
    category = "ios"
    description = "Xcode (pinned in catalog.toml) via xcodes; license accepted, first launch run."
    profiles = _IOS
    families: ClassVar[tuple[str, ...]] = _MACOS
    gui = True
    #: M5-D5: `sudo xcodebuild -license accept / -runFirstLaunch` (and xcodes `--select`).
    needs_sudo_on_macos: ClassVar[bool] = True
    requires = (Homebrew, Xcodes)
    per_os: ClassVar[OsMap[Installer]] = OsMap(macos=_XcodeInstall())

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        return _supported(os_info)


def _has_runtime(simctl_out: str, runtime: str) -> bool:
    """`iOS 27.0 (27.0 - 23A5287e) - com.apple…` is listed and not marked unavailable."""
    return any(
        line.startswith(f"{runtime} ") and "(unavailable" not in line
        for line in simctl_out.splitlines()
    )


@dataclass(frozen=True)
class _IosToolingInstall:
    def verify(self, ctx: Ctx) -> bool:
        runtime = f"iOS {xcode_pin().ios_runtime}"
        if not (pkg.installed(ctx, "cocoapods") and pkg.installed(ctx, "watchman")):
            return False
        sims = ctx.ex.run(["xcrun", "simctl", "list", "runtimes"])
        return sims.ok and _has_runtime(sims.stdout, runtime)

    def install(self, ctx: Ctx) -> None:
        runtime = f"iOS {xcode_pin().ios_runtime}"
        pkg.install(ctx, "cocoapods", "watchman")
        _require_auth("Downloading the iOS simulator runtime")
        _run_xcodes(ctx, "ios-tooling", ["xcodes", "runtimes", "install", runtime])


@register
class IosTooling(Module):
    name = "ios-tooling"
    category = "ios"
    description = "CocoaPods, watchman and the pinned iOS simulator runtime."
    profiles = _IOS
    families: ClassVar[tuple[str, ...]] = _MACOS
    requires = (Xcode,)
    per_os: ClassVar[OsMap[Installer]] = OsMap(macos=_IosToolingInstall())

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        return _supported(os_info)
