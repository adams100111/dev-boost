from __future__ import annotations

import os
import plistlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer
from devboost.modules import _launchd_jobs as jobs
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.system import ResticBackup
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _plist(home: Path, name: str) -> dict[str, object]:
    path = home / "Library" / "LaunchAgents" / f"dev.devboost.{name}.plist"
    return plistlib.loads(path.read_bytes())  # type: ignore[no-any-return]


def test_launchd_path_puts_user_and_brew_bins_first(tmp_path: Path) -> None:
    assert jobs.launchd_path().split(":") == [
        str(tmp_path / ".local" / "bin"), "/opt/homebrew/bin", "/opt/homebrew/sbin",
        "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]


def test_schedule_job_writes_an_hourly_agent(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert jobs.schedule_job(ctx, "aspire-gc", "devboost dev gc", "hourly") is True
    data = _plist(tmp_path, "aspire-gc")
    assert data["Label"] == "dev.devboost.aspire-gc"
    assert data["ProgramArguments"] == ["/bin/sh", "-c", "devboost dev gc"]
    assert data["StartCalendarInterval"] == {"Minute": 0}
    assert data["EnvironmentVariables"] == {"PATH": jobs.launchd_path()}
    log = str(tmp_path / "Library" / "Logs" / "devboost" / "aspire-gc.log")
    assert data["StandardOutPath"] == log and data["StandardErrorPath"] == log
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.aspire-gc.plist"
    bootstrap = ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)]
    assert bootstrap in ctx.ex.calls  # type: ignore[attr-defined]


def test_daily_is_midnight_like_systemd(tmp_path: Path) -> None:
    jobs.schedule_job(Ctx(os=MAC, ex=FakeExecutor()), "x", "true", "daily")
    assert _plist(tmp_path, "x")["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}


def test_job_scheduled_compares_the_whole_plist(tmp_path: Path) -> None:
    """M4-D7: verify uses agent_current with the same kwargs, so a drifted job is redone."""
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert jobs.job_scheduled(ctx, "x", "true", "daily") is False
    jobs.schedule_job(ctx, "x", "true", "daily")
    assert jobs.job_scheduled(ctx, "x", "true", "daily") is True
    assert jobs.job_scheduled(ctx, "x", "true", "hourly") is False
    assert jobs.job_scheduled(ctx, "x", "false", "daily") is False


def test_an_unchanged_job_is_not_reloaded() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert jobs.schedule_job(ctx, "x", "true", "daily") is True
    assert jobs.schedule_job(ctx, "x", "true", "daily") is False


def test_timer_is_an_installer_that_brews_what_it_needs() -> None:
    timer = jobs.LaunchdTimer("restic-backup", "exec restic snapshots", "daily", ("restic",))
    assert isinstance(timer, Installer)
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    timer.install(ctx)
    assert ["brew", "install", "--formula", "-y", "restic"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_a_timer_without_formulae_never_runs_brew() -> None:
    timer = jobs.LaunchdTimer("t", "true", "hourly")
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    timer.install(ctx)
    assert not any(c[0] == "brew" for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_uses_brew_follows_the_formulae() -> None:
    """M4-D9 / C-R19: a brewing strategy says so, and its module must require Homebrew."""
    assert jobs.LaunchdTimer("t", "true", "hourly", ("restic",)).uses_brew is True
    assert jobs.LaunchdTimer("t", "true", "hourly").uses_brew is False
    assert [c.name for c in ResticBackup.requires] == ["homebrew"]


def test_timer_verify_needs_formula_and_loaded_job() -> None:
    timer = jobs.LaunchdTimer("t", "true", "hourly", ("restic",))
    ok = Ctx(os=MAC, ex=RuleExecutor())
    assert timer.verify(ok) is False  # no plist yet
    timer.install(ok)
    assert timer.verify(ok) is True
    no_formula = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    assert timer.verify(no_formula) is False
    unloaded = Ctx(os=MAC, ex=RuleExecutor(rules=[(("launchctl", "print"), Result(113))]))
    assert timer.verify(unloaded) is False


def test_aspire_gc_on_macos_is_an_hourly_agent(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    AspireGc().install(ctx)
    assert _plist(tmp_path, "aspire-gc")["ProgramArguments"] == [
        "/bin/sh", "-c", "devboost dev gc"
    ]
    assert not (tmp_path / ".config" / "systemd").exists()
    assert AspireGc().verify(ctx) is True


def test_restic_backup_on_macos_is_a_daily_agent_resolving_restic_via_path(
    tmp_path: Path,
) -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    ResticBackup().install(ctx)
    data = _plist(tmp_path, "restic-backup")
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    script = data["ProgramArguments"][2]  # type: ignore[index]
    assert script == 'exec restic backup --files-from "$HOME/.config/devboost/restic-include"'
    assert "/usr/bin/restic" not in script
    assert ResticBackup().verify(ctx) is True


def test_linux_timers_are_unchanged(tmp_path: Path) -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    AspireGc().install(ctx)
    assert (tmp_path / ".config" / "systemd" / "user" / "aspire-gc.timer").exists()
    assert not (tmp_path / "Library").exists()
