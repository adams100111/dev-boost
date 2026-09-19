"""A macOS run asks for sudo only when a pending module needs it (ruling C-R3)."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from typing import Any

import pytest
import typer

from devboost.cli import app as cli_app
from devboost.cli import host as plat
from devboost.core import log
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


def test_only_the_foundation_modules_and_tailscale_need_sudo_on_macos() -> None:
    # tailscale: its cask is a .pkg, which brew installs with sudo (ruling C-R21).
    # M5-D5: macos-limits (system_daemon + `sudo sh`), macos-firewall (`sudo
    # socketfilterfw`) and xcode (`sudo xcodebuild -license accept` / `-runFirstLaunch`)
    # all run sudo too.
    flagged = {name for name, cls in load().items() if cls.needs_sudo_on_macos}
    assert flagged == {
        "xcode-clt", "homebrew", "rosetta", "tailscale",
        "macos-limits", "macos-firewall", "xcode",
    }
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


def test_needs_sudo_false_under_force_when_the_foundation_is_present() -> None:
    # Forced foundation installs are no-ops when present: nothing runs sudo.
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_VERIFIED)), force=True)
    plan = _plan("xcode-clt", "homebrew", "rosetta")
    assert cli_app._needs_sudo(plan, load(), ctx) is False
    assert cli_app._needs_sudo(plan, load(), ctx, forced={"homebrew"}) is False


def test_needs_sudo_false_when_only_brew_analytics_are_on() -> None:
    answers = {**_VERIFIED, ("brew", "analytics", "state"): Result(0, stdout="enabled")}
    ctx = Ctx(os=MAC, ex=Scripted(answers=answers))
    assert cli_app._needs_sudo(_plan("xcode-clt", "homebrew"), load(), ctx) is False


def test_needs_sudo_under_force_reaches_only_the_forced_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default probe counts a forced module as pending; one not forced is probed as is.
    seen: list[bool] = []

    def _probe(self: object, ctx: Ctx) -> bool:
        seen.append(ctx.force)
        return ctx.force

    monkeypatch.setattr(Homebrew, "sudo_needed", _probe)
    ctx = Ctx(os=MAC, ex=Scripted(answers=dict(_VERIFIED)), force=True)
    assert cli_app._needs_sudo(_plan("homebrew"), load(), ctx, forced={"jq"}) is False
    assert cli_app._needs_sudo(_plan("homebrew"), load(), ctx, forced={"homebrew"}) is True
    assert cli_app._needs_sudo(_plan("homebrew"), load(), ctx, forced=None) is True
    assert seen == [False, True, True]


def test_needs_sudo_treats_a_raising_probe_as_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(self: object, ctx: Ctx) -> bool:
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(Homebrew, "sudo_needed", _boom)
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

    def _fake_run_plan(
        plan: list[PlannedModule], modules: Any, ctx: Ctx, **_: Any
    ) -> list[Any]:
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


# --- --force / --offline end to end: the real runner, a fully set-up Mac -------------

#: A Mac with everything present: CLT (xcode-select -p ok), brew at /opt/homebrew with
#: analytics off, Rosetta, and every formula installed. softwareupdate offers no CLT.
_SET_UP: dict[tuple[str, ...], Result] = {
    **_VERIFIED,
    ("softwareupdate", "--list"): Result(0, stderr="No new software available.\n"),
    ("brew", "info"): Result(0, stdout='{"casks": [{"auto_updates": false}]}'),
}


def _wire_runner(
    monkeypatch: pytest.MonkeyPatch, answers: dict[tuple[str, ...], Result]
) -> tuple[list[list[str]], Scripted]:
    """Like `_wire`, but the REAL run_plan runs against one Scripted executor."""
    host_calls: list[list[str]] = []
    ex = Scripted(answers=dict(answers))

    def _fake_subprocess_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        host_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    monkeypatch.setattr("devboost.core.osinfo.detect", lambda: MAC)
    monkeypatch.setattr(cli_app, "RealExecutor", lambda: ex)
    monkeypatch.setattr("devboost.exec.primitives.pkg.refresh_index", lambda ctx: None)
    monkeypatch.setattr(plat, "keep_awake", lambda: host_calls.append(["caffeinate"]))
    monkeypatch.setattr("subprocess.run", _fake_subprocess_run)  # SudoKeepalive's sudo
    return host_calls, ex


def test_force_on_a_set_up_mac_blocks_nothing_and_never_asks_for_sudo(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # Final review I1: --force used to force xcode-clt too, whose softwareupdate offered
    # no CLT → NeedsUser → xcode-clt, homebrew and ripgrep all blocked, and a sudo prompt.
    host_calls, ex = _wire_runner(monkeypatch, _SET_UP)
    results = cli_app._run(["ripgrep"], profiles_file.parent, dry_run=False, force=True)
    status = {r.name: r.status for r in results}
    assert status == {"xcode-clt": "skip", "homebrew": "skip", "ripgrep": "ok"}
    assert ["sudo", "-v"] not in host_calls
    assert not any(c[:1] == ["softwareupdate"] for c in ex.calls)
    assert not any(c[:1] == ["sudo"] for c in ex.calls)
    assert ["brew", "upgrade", "--formula", "ripgrep"] in ex.calls  # the selection IS forced


def test_force_on_a_selected_foundation_module_is_a_no_op(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    host_calls, ex = _wire_runner(monkeypatch, _SET_UP)
    results = cli_app._run(
        ["xcode-clt", "rosetta"], profiles_file.parent, dry_run=False, force=True
    )
    assert {r.name: r.status for r in results} == {"xcode-clt": "ok", "rosetta": "ok"}
    assert ["sudo", "-v"] not in host_calls
    assert not any(c[:1] in (["softwareupdate"], ["sudo"]) for c in ex.calls)


def test_offline_on_a_mac_skips_network_modules_and_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # Homebrew missing: its installer needs the network, so --offline skips it — and a
    # skipped module is never a reason to ask for the password.
    host_calls, ex = _wire_runner(monkeypatch, {**_NO_BREW, ("xcode-select", "-p"): Result(0)})
    results = cli_app._run(
        ["homebrew"], profiles_file.parent, dry_run=False, force=False, offline=True
    )
    status = {r.name: (r.status, r.detail) for r in results}
    assert status["homebrew"] == ("skip", "needs-network")
    assert ["sudo", "-v"] not in host_calls
    assert not any(c[:1] == ["curl"] for c in ex.calls)


def test_without_a_sudo_prompt_mac_sudo_steps_fail_fast(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # Ruling C-R18: no password was asked for, so a sudo step runs as `sudo -n`.
    def _fake_run_plan(plan: Any, modules: Any, ctx: Ctx, **_: Any) -> list[Any]:
        ctx.ex.run(["true"], sudo=True)
        return []

    _, ex = _wire_runner(monkeypatch, _SET_UP)
    monkeypatch.setattr(cli_app, "run_plan", _fake_run_plan)
    cli_app._run(["homebrew"], profiles_file.parent, dry_run=False, force=False)
    assert ex.calls[-1] == ["sudo", "-n", "true"]


def test_with_a_sudo_prompt_mac_sudo_steps_use_the_cached_timestamp(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    def _fake_run_plan(plan: Any, modules: Any, ctx: Ctx, **_: Any) -> list[Any]:
        ctx.ex.run(["true"], sudo=True)
        return []

    host_calls, ex = _wire_runner(monkeypatch, _NO_BREW)
    monkeypatch.setattr(cli_app, "run_plan", _fake_run_plan)
    cli_app._run(["homebrew"], profiles_file.parent, dry_run=False, force=False)
    assert ["sudo", "-v"] in host_calls
    assert ex.calls[-1] == ["sudo", "true"]


def test_run_passes_the_final_plan_to_added_dependencies(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    seen: list[tuple[list[PlannedModule], list[str]]] = []
    real = cli_app._added_dependencies

    def _spy(plan: list[PlannedModule], selected: Any) -> list[str]:
        seen.append((list(plan), list(selected)))
        return real(plan, selected)

    _wire(monkeypatch, MAC, _VERIFIED)
    monkeypatch.setattr(cli_app, "_added_dependencies", _spy)
    cli_app._run(["ripgrep"], profiles_file.parent, dry_run=False, force=False)
    [(plan, selected)] = seen
    assert selected == ["ripgrep"]
    assert [pm.name for pm in plan] == ["xcode-clt", "homebrew", "ripgrep"]


def _infos(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(log, "info", seen.append)
    return seen


def test_update_on_a_mac_does_not_announce_dependencies_it_drops(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # Core review M1: xcode-clt and homebrew are dropped by the --update filter, so the
    # "+N required dependencies added" line must not name them.
    _, plans = _wire(monkeypatch, MAC, _VERIFIED)
    infos = _infos(monkeypatch)
    cli_app._run(["ripgrep"], profiles_file.parent, dry_run=False, force=False, update=True)
    assert [pm.name for pm in plans[0]] == ["ripgrep"]
    assert not any("required dependencies" in m for m in infos)


def test_install_announces_only_dependencies_that_will_run(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    _wire(monkeypatch, MAC, _VERIFIED)
    infos = _infos(monkeypatch)
    cli_app._run(["ripgrep"], profiles_file.parent, dry_run=False, force=False)
    assert "+2 required dependencies added: xcode-clt, homebrew" in infos


def test_added_dependencies_skips_entries_the_plan_only_skips() -> None:
    plan = [PlannedModule("curl", skip_reason="provided-by-macos"), *_plan("homebrew", "jq")]
    assert cli_app._added_dependencies(plan, ["jq"]) == ["homebrew"]


def test_update_with_nothing_to_refresh_says_so(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    _, plans = _wire(monkeypatch, FEDORA, {})
    infos = _infos(monkeypatch)
    cli_app._run(["docker"], profiles_file.parent, dry_run=False, force=False, update=True)
    assert plans == [[]]
    assert "nothing to update in selection" in infos


# --- AF1: sudo asked for but not granted (unattended run, no tty) ----------------------

#: CLT and brew present, Rosetta missing: `arch -x86_64` fails with "Bad CPU type".
_NO_ROSETTA: dict[tuple[str, ...], Result] = {
    **_SET_UP,
    ("arch", "-x86_64"): Result(1, stderr="Bad CPU type in executable"),
}


def _deny_sudo(monkeypatch: pytest.MonkeyPatch, host_calls: list[list[str]]) -> None:
    def _fake_subprocess_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        host_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 1)  # "sudo: a password is required"

    monkeypatch.setattr("subprocess.run", _fake_subprocess_run)


def _spy_run_plan(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Ctx], list[Any]]:
    """Record the ctx the runner gets and its results (kept even when _run exits 1)."""
    seen: list[Ctx] = []
    results: list[Any] = []
    from devboost.core.runner import run_plan as real

    def _spy(plan: Any, modules: Any, ctx: Ctx, **kw: Any) -> Any:
        seen.append(ctx)
        out = real(plan, modules, ctx, **kw)
        results.extend(out)
        return out

    monkeypatch.setattr(cli_app, "run_plan", _spy)
    return seen, results


def test_ungranted_sudo_blocks_a_pending_sudo_module_without_running_it(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # M3 acceptance AF1: rosetta ran `softwareupdate --install-rosetta` with no sudo and
    # ended as an error. It must be blocked with the fix, never attempted.
    host_calls, ex = _wire_runner(monkeypatch, _NO_ROSETTA)
    _deny_sudo(monkeypatch, host_calls)
    results = cli_app._run(["rosetta"], profiles_file.parent, dry_run=False, force=False)
    [rosetta] = [r for r in results if r.name == "rosetta"]
    assert ["sudo", "-v"] in host_calls
    assert rosetta.status == "blocked"
    assert "run `devboost install rosetta` in a terminal (needs your password)" in rosetta.detail
    assert not any(c[:1] == ["softwareupdate"] for c in ex.calls)
    assert not any("--install-rosetta" in c for c in ex.calls)


def test_ungranted_sudo_still_runs_steps_that_need_no_root(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    # Homebrew present with analytics on: `brew analytics off` needs no root, so a
    # session without sudo still runs it; a stray sudo step fails fast (C-R18).
    answers = {**_NO_ROSETTA, ("brew", "analytics", "state"): Result(0, stdout="enabled")}
    host_calls, ex = _wire_runner(monkeypatch, answers)
    _deny_sudo(monkeypatch, host_calls)
    seen, results = _spy_run_plan(monkeypatch)
    with contextlib.suppress(typer.Exit):  # the scripted analytics state never flips
        cli_app._run(["homebrew", "rosetta"], profiles_file.parent, dry_run=False, force=False)
    status = {r.name: r.status for r in results}
    assert status["rosetta"] == "blocked"
    assert status["homebrew"] != "blocked"
    assert ["brew", "analytics", "off"] in ex.calls
    assert seen[0].no_sudo is True
    seen[0].ex.run(["true"], sudo=True)
    assert ex.calls[-1] == ["sudo", "-n", "true"]


def test_granted_sudo_runs_the_sudo_module(
    monkeypatch: pytest.MonkeyPatch, profiles_file: Path
) -> None:
    host_calls, ex = _wire_runner(monkeypatch, _NO_ROSETTA)
    _, results = _spy_run_plan(monkeypatch)
    with contextlib.suppress(typer.Exit):  # the scripted `arch` never starts working
        cli_app._run(["rosetta"], profiles_file.parent, dry_run=False, force=False)
    assert ["sudo", "-v"] in host_calls
    assert ["sudo", "softwareupdate", "--install-rosetta", "--agree-to-license"] in ex.calls
    assert {r.name: r.status for r in results}["rosetta"] != "blocked"


def test_mac_session_yields_whether_sudo_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plat, "keep_awake", lambda: None)
    for code, held in ((0, True), (1, False)):
        monkeypatch.setattr(
            "subprocess.run",
            lambda argv, _c=code, **_: subprocess.CompletedProcess(argv, _c),
        )
        with plat.mac_session(MAC, dry_run=False, sudo=True) as got:
            assert got is held
    with plat.mac_session(MAC, dry_run=False, sudo=False) as got:
        assert got is False
    with plat.mac_session(FEDORA, dry_run=False) as got:
        assert got is True
