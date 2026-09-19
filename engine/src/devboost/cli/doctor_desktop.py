"""doctor — the macOS desktop checks (spec §8, desktop half; D22).

Only a disabled firewall fails, and only once macos-firewall has turned it on here (its
marker): then dev-boost manages it and "off" is drift. Otherwise it is a WARN. FileVault, SIP,
Time Machine, iCloud Desktop & Documents and the battery charge limit are the user's
choice, so they are reported as WARN/hint lines that never fail `doctor`. A probe that
fails is reported as WARN too: doctor must not reassure on a check it could not make.

``doctor.run_checks`` calls ``checks(ctx)`` from its macOS branch (ruling M5-D14).
"""

from __future__ import annotations

from devboost.cli.doctor import Check
from devboost.core.errors import DevbootError
from devboost.core.macver import macos_version
from devboost.core.registry import load
from devboost.exec.primitives import macdefaults, pkg
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from devboost.modules.macos_system import firewall_enabled, firewall_marker

#: The first macOS with a battery charge limit (System Settings → Battery → Charging).
_CHARGE_LIMIT_SINCE = (26, 4)


def _firewall(ctx: Ctx) -> Check:
    if firewall_enabled(ctx):
        return Check("firewall", True, "on")
    if firewall_marker().exists():
        return Check("firewall", False, "off — dev-boost turned it on earlier; run "
                     "`devboost install macos-firewall`")
    return Check("firewall", True,
                 "WARN off — `devboost install macos-firewall` turns it on")


def _filevault(ctx: Ctx) -> Check:
    on = "FileVault is On" in ctx.ex.run(["fdesetup", "status"]).stdout
    return Check("filevault", True, "on" if on else
                 "WARN off — System Settings → Privacy & Security → FileVault")


def _sip(ctx: Ctx) -> Check:
    on = "status: enabled" in ctx.ex.run(["csrutil", "status"]).stdout
    return Check("sip", True, "enabled" if on else
                 "WARN disabled — re-enable from Recovery: csrutil enable")


def _time_machine(ctx: Ctx) -> Check:
    res = ctx.ex.run(["tmutil", "destinationinfo"])
    none = not res.ok or "No destinations configured" in res.stdout + res.stderr
    return Check("time-machine", True,
                 "WARN no backup destination — System Settings → General → Time Machine"
                 if none else "destination configured")


def _icloud_desktop(ctx: Ctx) -> Check:
    on = macdefaults.read(ctx, "com.apple.finder", "FXICloudDriveDesktop") == Value("bool", True)
    return Check("icloud-desktop", True,
                 "WARN iCloud Desktop & Documents is on — keep repos out of ~/Desktop and "
                 "~/Documents (node_modules churn)" if on else "off")


def _charge_limit(ctx: Ctx) -> Check:
    v = macos_version(ctx.os)
    if v is None or v < _CHARGE_LIMIT_SINCE:
        return Check("charge-limit", True, "n/a")
    if "InternalBattery" not in ctx.ex.run(["pmset", "-g", "batt"]).stdout:
        return Check("charge-limit", True, "n/a")
    return Check("charge-limit", True,
                 "hint: set a charge limit — System Settings → Battery → Charging (no CLI)")


def _hotkeys(ctx: Ctx) -> Check:
    hints: list[str] = []
    if pkg.cask_installed(ctx, "raycast"):
        hints.append("Raycast: free ⌘Space (System Settings → Keyboard → Keyboard Shortcuts "
                     "→ Spotlight), then set it as Raycast's hotkey")
    if pkg.cask_installed(ctx, "maccy"):
        hints.append("Maccy: ⇧⌘C opens clipboard history")
    return Check("hotkeys", True, "; ".join(hints) or "none")


def _gated(ctx: Ctx) -> Check:
    gated: list[str] = []
    unknown: list[str] = []
    for name, cls in sorted(load().items()):
        if cls.families and "macos" not in cls.families:
            continue
        try:
            if not cls.supported_on(ctx.os):
                gated.append(name)
        except DevbootError:  # e.g. xcode's pin: catalog.toml missing or invalid
            unknown.append(name)
    parts: list[str] = []
    if unknown:
        parts.append(f"WARN could not check {', '.join(unknown)} (catalog.toml missing or "
                     "invalid)")
    if gated:
        parts.append(", ".join(gated) + " — not supported on this macOS version")
    return Check("version-gated", True, "; ".join(parts) or "none")


def checks(ctx: Ctx) -> list[Check]:
    """The desktop checks, in report order. Only ``firewall`` can be ``ok=False``."""
    return [
        _firewall(ctx), _filevault(ctx), _sip(ctx), _time_machine(ctx),
        _icloud_desktop(ctx), _charge_limit(ctx), _hotkeys(ctx), _gated(ctx),
    ]


#: The plan's name for ``checks`` (Task 16 brief).
desktop_checks = checks
