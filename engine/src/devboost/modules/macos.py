"""macOS foundations: Command Line Tools, Homebrew, Rosetta 2 (spec §0, §2).

Every module whose macOS install uses Homebrew `requires` Homebrew, which requires the
CLT. All three are `families = ("macos",)`, so Linux plans drop them.
"""

from __future__ import annotations

import json
import re
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.exec.primitives import remote_script
from devboost.exec.primitives.pkg import BREW_ENV
from devboost.model import Ctx, Module

_MACOS: tuple[str, ...] = ("macos",)

CLT_DIR = "/Library/Developer/CommandLineTools"
#: While this file exists, `softwareupdate --list` offers the CLT (Homebrew's installer
#: uses the same trick); otherwise only the GUI prompt of `xcode-select --install` does.
CLT_PLACEHOLDER = "/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress"
BREW_INSTALLER = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
BREW_PREFIX = "/opt/homebrew"
#: Rosetta 2 runs amd64 container images (Docker/Colima VMs) and Intel-only tools and apps.
#: Apple's 2026-09-01 notice: macOS 27 is the last full Rosetta release; from 28 it is
#: limited to legacy games, so there is nothing to install and doctor lists what breaks.
ROSETTA_LAST_FULL_MAJOR = 27

_LABEL = re.compile(r"^\s*\*\s*Label:\s*(Command Line Tools.*?)\s*$")


def clt_label(listing: str) -> str | None:
    """The newest "Command Line Tools …" label in `softwareupdate --list` output."""
    labels = [m.group(1) for line in listing.splitlines() if (m := _LABEL.match(line))]
    if not labels:
        return None
    return max(labels, key=lambda label: tuple(int(n) for n in re.findall(r"\d+", label)))


def mac_major(os_info: OsInfo) -> int:
    """The macOS major version ("27.0" → 27); 0 when unknown."""
    head = os_info.version_id.split(".", 1)[0]
    return int(head) if head.isdigit() else 0


def rosetta_supported(os_info: OsInfo) -> bool:
    major = mac_major(os_info)
    return major == 0 or major <= ROSETTA_LAST_FULL_MAJOR


def rosetta_present(ctx: Ctx) -> bool:
    # Fails with "Bad CPU type in executable" when Rosetta is not installed.
    return ctx.ex.run(["arch", "-x86_64", "/usr/bin/true"]).ok


def intel_only_apps(ctx: Ctx) -> list[str]:
    """Installed apps that are Intel-only (they need Rosetta)."""
    res = ctx.ex.run(["system_profiler", "-json", "SPApplicationsDataType"])
    if not res.ok:
        return []
    try:
        items = json.loads(res.stdout).get("SPApplicationsDataType", [])
    except (ValueError, AttributeError):
        return []
    return sorted({
        str(i["_name"])
        for i in items
        if isinstance(i, dict) and i.get("arch_kind") == "arch_i64" and "_name" in i
    })


@register
class XcodeClt(Module):
    name = "xcode-clt"
    category = "base"
    description = "Xcode Command Line Tools (clang, make, git) — installed without a dialog."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)
    needs_sudo_on_macos: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["xcode-select", "-p"]).ok

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["touch", CLT_PLACEHOLDER], sudo=True)
        try:
            listing = ctx.ex.run(["softwareupdate", "--list"])
            label = clt_label(listing.stdout + "\n" + listing.stderr)
            if label is None:
                raise NeedsUser(
                    "softwareupdate offers no Command Line Tools package",
                    "run `xcode-select --install`, click Install, then re-run devboost",
                )
            res = ctx.ex.run(["softwareupdate", "--install", label], sudo=True)
            if not res.ok:
                raise InstallError(self.name, f"softwareupdate --install {label!r}", res.code)
            ctx.ex.run(["xcode-select", "--switch", CLT_DIR], sudo=True)
        finally:
            ctx.ex.run(["rm", "-f", CLT_PLACEHOLDER], sudo=True)


@register
class Homebrew(Module):
    name = "homebrew"
    category = "base"
    description = "Homebrew — the macOS package manager (analytics off)."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)
    needs_sudo_on_macos: ClassVar[bool] = True
    requires = (XcodeClt,)

    def _present(self, ctx: Ctx) -> bool:
        res = ctx.ex.run(["brew", "--prefix"], env=BREW_ENV)
        return res.ok and res.stdout.strip() == BREW_PREFIX

    def verify(self, ctx: Ctx) -> bool:
        if not self._present(ctx):
            return False
        state = ctx.ex.run(["brew", "analytics", "state"], env=BREW_ENV)
        return state.ok and "analytics are disabled" in state.stdout.lower()

    def install(self, ctx: Ctx) -> None:
        if not self._present(ctx):
            # NONINTERACTIVE: no "press RETURN"; it uses the sudo timestamp the macOS run
            # session (cli/host.py SudoKeepalive, started because this module sets
            # needs_sudo_on_macos) already holds. Never run as root.
            remote_script.run_script(
                ctx, self.name, BREW_INSTALLER, "/bin/bash", env={"NONINTERACTIVE": "1"}
            )
        res = ctx.ex.run(["brew", "analytics", "off"], env=BREW_ENV)
        if not res.ok:
            raise InstallError(self.name, "brew analytics off", res.code)


@register
class Rosetta(Module):
    """Rosetta 2: needed for amd64 container images and Intel-only tools (macOS <= 27).

    Sunset: macOS 27 is the last full Rosetta release (Apple notice 2026-09-01).
    """

    name = "rosetta"
    category = "base"
    description = "Rosetta 2 — runs Intel-only apps and fast amd64 containers (macOS ≤ 27)."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)
    needs_sudo_on_macos: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        # From macOS 28 Rosetta is limited to legacy games: nothing to install; `devboost
        # doctor` lists the Intel-only apps that will stop working.
        return not rosetta_supported(ctx.os) or rosetta_present(ctx)

    def install(self, ctx: Ctx) -> None:
        if not rosetta_supported(ctx.os):
            log.warn(f"rosetta: limited on macOS {ctx.os.version_id} — see `devboost doctor`")
            return
        argv = ["softwareupdate", "--install-rosetta", "--agree-to-license"]
        res = ctx.ex.run(argv, sudo=True)
        if not res.ok:
            raise InstallError(self.name, " ".join(argv), res.code)
