from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from devboost.cli import doctor_desktop
from devboost.cli.doctor import run_checks
from devboost.cli.doctor_desktop import desktop_checks
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx, Module
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC15 = OsInfo("macos", "macos", "aarch64", version_id="15.6")
MAC26_3 = OsInfo("macos", "macos", "aarch64", version_id="26.3")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]
FW_ON = (("--getglobalstate",), Result(0, "Firewall is enabled. (State = 1)\n"))
FW_OFF = (("--getglobalstate",), Result(0, "Firewall is disabled. (State = 0)\n"))
BATTERY = (("pmset",), Result(0, " -InternalBattery-0 (id=1)\t63%; discharging\n"))


def _checks(ex: RuleExecutor, os_info: OsInfo = MAC) -> dict[str, tuple[bool, str]]:
    return {c.name: (c.ok, c.detail) for c in desktop_checks(Ctx(os=os_info, ex=ex))}


def test_the_ruling_entry_point_is_checks() -> None:
    # M5-D14: doctor's macOS branch calls `doctor_desktop.checks(ctx)`.
    assert doctor_desktop.checks is desktop_checks


def test_the_check_names() -> None:
    assert list(_checks(RuleExecutor(rules=[FW_ON]))) == [
        "firewall", "filevault", "sip", "time-machine", "icloud-desktop", "charge-limit",
        "hotkeys", "version-gated",
    ]


def test_firewall_off_fails() -> None:
    off = _checks(RuleExecutor(rules=[FW_OFF]))["firewall"]
    assert off[0] is False and "devboost install macos-firewall" in off[1]
    assert _checks(RuleExecutor(rules=[FW_ON]))["firewall"] == (True, "on")


def test_everything_else_warns_without_failing() -> None:
    ex = RuleExecutor(rules=[
        FW_ON,
        (("fdesetup",), Result(0, "FileVault is Off.\n")),
        (("csrutil",), Result(0, "System Integrity Protection status: disabled.\n")),
        (("destinationinfo",), Result(0, "tmutil: No destinations configured.\n")),
        (("read-type", "FXICloudDriveDesktop"), Result(0, "Type is boolean\n")),
        (("FXICloudDriveDesktop",), Result(0, "1\n")),
        BATTERY,
    ])
    got = _checks(ex)
    assert all(ok for ok, _ in got.values())
    for name in ("filevault", "sip", "time-machine", "icloud-desktop"):
        assert got[name][1].startswith("WARN"), name
    assert got["charge-limit"][1].startswith("hint:")
    assert "Raycast" in got["hotkeys"][1] and "Maccy" in got["hotkeys"][1]


def test_healthy_mac_reads_clean() -> None:
    ex = RuleExecutor(rules=[
        FW_ON,
        (("fdesetup",), Result(0, "FileVault is On.\n")),
        (("csrutil",), Result(0, "System Integrity Protection status: enabled.\n")),
        (("destinationinfo",), Result(0, "Name : Backup\nKind : Local\n")),
        (("read-type",), Result(1)),
        (("pmset",), Result(0, "Now drawing from 'AC Power'\n")),
        (("brew", "list"), Result(1)),
    ])
    got = _checks(ex)
    assert not any(detail.startswith("WARN") for _, detail in got.values())
    assert got["filevault"][1] == "on" and got["sip"][1] == "enabled"
    assert got["time-machine"][1] == "destination configured"
    assert got["icloud-desktop"][1] == "off"
    assert got["charge-limit"][1] == "n/a"
    assert got["hotkeys"][1] == "none"


def test_failing_probes_warn_rather_than_reassure() -> None:
    ex = RuleExecutor(rules=[FW_ON, (("fdesetup",), Result(1)), (("csrutil",), Result(1)),
                             (("destinationinfo",), Result(1))])
    got = _checks(ex)
    for name in ("filevault", "sip", "time-machine"):
        assert got[name][0] is True and got[name][1].startswith("WARN"), name


def test_charge_limit_hint_needs_a_battery_and_macos_26_4() -> None:
    assert _checks(RuleExecutor(rules=[FW_ON, BATTERY]), MAC26_3)["charge-limit"][1] == "n/a"
    assert _checks(RuleExecutor(rules=[FW_ON, BATTERY]))["charge-limit"][1].startswith("hint:")


class _Gated(Module):
    name = "gated-app"
    families: ClassVar[tuple[str, ...]] = ("macos",)

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        return v is not None and v >= (26, 0)


class _LinuxOnly(Module):
    name = "linux-only"
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        return False


def test_version_gated_modules_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real gated modules (thaw, xcode) land in other M5 lanes; use stand-ins here.
    monkeypatch.setattr(doctor_desktop, "load",
                        lambda: {"gated-app": _Gated, "linux-only": _LinuxOnly})
    detail = _checks(RuleExecutor(rules=[FW_ON]), MAC15)["version-gated"][1]
    assert detail == "gated-app — not supported on this macOS version"
    assert _checks(RuleExecutor(rules=[FW_ON]))["version-gated"][1] == "none"


def test_run_checks_includes_the_desktop_on_macos() -> None:
    names = {c.name for c in run_checks(Ctx(os=MAC, ex=RuleExecutor(rules=[FW_ON])), REPO_ROOT)}
    assert {"firewall", "filevault", "version-gated", "rosetta"} <= names


def test_run_checks_has_no_desktop_checks_on_linux() -> None:
    names = {c.name for c in run_checks(Ctx(os=FEDORA, ex=RuleExecutor()), REPO_ROOT)}
    assert not names & {"firewall", "filevault", "version-gated"}
