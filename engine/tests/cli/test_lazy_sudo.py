"""A macOS run asks for sudo only when a pending module needs it (ruling C-R3)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from devboost.cli import app as cli_app
from devboost.cli import host as plat
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.registry import load
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules.macos import Homebrew, Rosetta, XcodeClt
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

#: Every foundation module verifies: CLT present, brew at /opt/homebrew with analytics
#: off, Rosetta runs x86_64 binaries.
_VERIFIED: dict[tuple[str, ...], Result] = {
    ("brew", "--prefix"): Result(0, stdout="/opt/homebrew\n"),
    ("brew", "analytics", "state"): Result(0, stdout="InfluxDB analytics are disabled.\n"),
}
#: CLT and Rosetta present, Homebrew missing (every brew call: command not found).
_NO_BREW: dict[tuple[str, ...], Result] = {("brew",): Result(127)}


def test_only_the_foundation_modules_need_sudo_on_macos() -> None:
    flagged = {name for name, cls in load().items() if cls.needs_sudo_on_macos}
    assert flagged == {"xcode-clt", "homebrew", "rosetta"}
    assert XcodeClt.needs_sudo_on_macos and Homebrew.needs_sudo_on_macos
    assert Rosetta.needs_sudo_on_macos


def _plan(*names: str) -> list[PlannedModule]:
    return [PlannedModule(name=n) for n in names]


def test_needs_sudo_false_when_everything_verifies() -> None:
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_VERIFIED)))
    plan = _plan("xcode-clt", "homebrew", "rosetta")
    assert cli_app._needs_sudo(plan, load(), ctx) is False


def test_needs_sudo_true_when_homebrew_is_pending() -> None:
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_NO_BREW)))
    assert cli_app._needs_sudo(_plan("xcode-clt", "homebrew"), load(), ctx) is True


def test_needs_sudo_ignores_skipped_and_unflagged_modules() -> None:
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_NO_BREW)))
    plan = [PlannedModule(name="homebrew", skip_reason="needs-network"), *_plan("jq")]
    assert cli_app._needs_sudo(plan, load(), ctx) is False


def test_needs_sudo_true_under_force_even_when_verified() -> None:
    # --force reinstalls without consulting verify, so the installer's sudo steps run.
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_VERIFIED)), force=True)
    assert cli_app._needs_sudo(_plan("rosetta"), load(), ctx) is True


def test_needs_sudo_treats_a_raising_verify_as_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(self: object, ctx: Ctx) -> bool:
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(Homebrew, "verify", _boom)
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_VERIFIED)))
    assert cli_app._needs_sudo(_plan("homebrew"), load(), ctx) is True


# --- end to end through cli.app._run ----------------------------------------------


def _wire(
    monkeypatch: pytest.MonkeyPatch, os_info: OsInfo, answers: dict[tuple[str, ...], Result]
) -> tuple[list[list[str]], list[list[PlannedModule]]]:
    """Run `_run` hermetically; returns (host commands run, plans handed to the runner)."""
    host_calls: list[list[str]] = []
    plans: list[list[PlannedModule]] = []

    def _fake_subprocess_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        host_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    def _fake_run_plan(plan: list[PlannedModule], modules: Any, ctx: Ctx) -> list[Any]:
        plans.append(plan)
        return []

    monkeypatch.setattr("devboost.core.osinfo.detect", lambda: os_info)
    monkeypatch.setattr(cli_app, "RealExecutor", lambda: Scripted(answers=dict(answers)))
    monkeypatch.setattr(cli_app, "run_plan", _fake_run_plan)
    monkeypatch.setattr("devboost.exec.primitives.pkg.refresh_index", lambda ctx: None)
    monkeypatch.setattr(plat, "keep_awake", lambda: host_calls.append(["caffeinate"]))
    monkeypatch.setattr("subprocess.run", _fake_subprocess_run)  # SudoKeepalive's sudo
    return host_calls, plans


def test_run_on_a_set_up_mac_never_asks_for_sudo(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    host_calls, plans = _wire(monkeypatch, MAC, _VERIFIED)
    cli_app._run(["homebrew", "rosetta"], profiles_file.parent, dry_run=False, force=False)
    assert ["sudo", "-v"] not in host_calls
    assert ["caffeinate"] in host_calls  # still kept awake
    assert plans and {pm.name for pm in plans[0]} >= {"xcode-clt", "homebrew", "rosetta"}


def test_run_asks_for_sudo_when_homebrew_is_pending(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    host_calls, _ = _wire(monkeypatch, MAC, _NO_BREW)
    cli_app._run(["homebrew"], profiles_file.parent, dry_run=False, force=False)
    assert ["sudo", "-v"] in host_calls


def test_dry_run_never_asks_for_sudo(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    host_calls, _ = _wire(monkeypatch, MAC, _NO_BREW)
    cli_app._run(["homebrew"], profiles_file.parent, dry_run=True, force=False)
    assert host_calls == []


def test_linux_run_is_unaffected(monkeypatch: pytest.MonkeyPatch, profiles_file: Path) -> None:
    host_calls, plans = _wire(monkeypatch, FEDORA, _NO_BREW)
    cli_app._run(["jq"], profiles_file.parent, dry_run=False, force=False)
    assert host_calls == []
    assert [pm.name for pm in plans[0]] == ["jq"]


def test_mac_session_without_sudo_keeps_awake_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(plat, "keep_awake", lambda: seen.append("caffeinate"))
    monkeypatch.setattr(plat, "SudoKeepalive", lambda: pytest.fail("sudo was requested"))
    with plat.mac_session(MAC, dry_run=False, sudo=False):
        pass
    assert seen == ["caffeinate"]
