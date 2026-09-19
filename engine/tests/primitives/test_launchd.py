from __future__ import annotations

import os
import plistlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx

MAC = OsInfo("macos", "macos", "aarch64")
UID = os.getuid()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    return tmp_path


def test_label_namespacing() -> None:
    assert launchd.label("pass-sync") == "dev.devboost.pass-sync"


def test_agent_loaded() -> None:
    assert launchd.agent_loaded(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x") is True
    ex_fail = FakeExecutor(scripts={"launchctl": Result(1)})
    assert launchd.agent_loaded(Ctx(os=MAC, ex=ex_fail), "dev.devboost.x") is False


def test_daemon_loaded() -> None:
    assert launchd.daemon_loaded(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x") is True
    ex_fail = FakeExecutor(scripts={"launchctl": Result(1)})
    assert launchd.daemon_loaded(Ctx(os=MAC, ex=ex_fail), "dev.devboost.x") is False


def test_user_agent_writes_plist_and_bootstraps(home: Path) -> None:
    ex = FakeExecutor()  # no plist yet → written and bootstrapped
    changed = launchd.user_agent(
        Ctx(os=MAC, ex=ex), "dev.devboost.x", ["/usr/bin/true", "a"],
        start_interval=900, env={"K": "V"}, run_at_load=True,
    )
    plist = home / "Library" / "LaunchAgents" / "dev.devboost.x.plist"
    data = plistlib.loads(plist.read_bytes())
    assert data == {
        "Label": "dev.devboost.x",
        "ProgramArguments": ["/usr/bin/true", "a"],
        "StartInterval": 900,
        "RunAtLoad": True,
        "EnvironmentVariables": {"K": "V"},
    }
    assert changed is True
    assert ["launchctl", "bootstrap", f"gui/{UID}", str(plist)] in ex.calls


def test_user_agent_idempotent_when_unchanged_and_loaded(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())  # launchctl print → ok (loaded)
    launchd.user_agent(ctx, "dev.devboost.x", ["/usr/bin/true"])
    ex2 = FakeExecutor()
    assert launchd.user_agent(Ctx(os=MAC, ex=ex2), "dev.devboost.x", ["/usr/bin/true"]) is False
    assert ex2.calls == [["launchctl", "print", f"gui/{UID}/dev.devboost.x"]]


def test_user_agent_calendar(home: Path) -> None:
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.y", ["/bin/echo"],
        start_calendar={"Hour": 3, "Minute": 0},
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.y.plist").read_bytes())
    assert data["StartCalendarInterval"] == {"Hour": 3, "Minute": 0}


def test_user_agent_bootstrap_failure_raises(home: Path) -> None:
    ex = FakeExecutor(scripts={"launchctl": Result(5)})
    with pytest.raises(InstallError):
        launchd.user_agent(Ctx(os=MAC, ex=ex), "dev.devboost.z", ["/bin/echo"])


def test_system_daemon_writes_via_sudo_and_bootstraps_system_domain(home: Path) -> None:
    path = home / "LaunchDaemons" / "dev.devboost.limits.plist"
    # not loaded: make `launchctl print` fail but bootstrap succeed
    calls: list[list[str]] = []

    class _Ex(FakeExecutor):
        def run(
            self,
            argv: Sequence[str],
            *,
            sudo: bool = False,
            stdin: str | None = None,
            env: Mapping[str, str] | None = None,
            cwd: Path | None = None,
            interactive: bool = False,
        ) -> Result:
            calls.append((["sudo"] if sudo else []) + list(argv))
            return Result(1) if argv[:2] == ["launchctl", "print"] else Result(0)

    launchd.system_daemon(
        Ctx(os=MAC, ex=_Ex()),
        "dev.devboost.limits",
        ["/bin/launchctl", "limit"],
    )
    assert ["sudo", "tee", str(path)] in calls
    assert ["sudo", "chown", "root:wheel", str(path)] in calls
    assert ["sudo", "chmod", "644", str(path)] in calls
    assert ["sudo", "launchctl", "bootstrap", "system", str(path)] in calls


def test_remove_agent_bootouts_and_deletes(home: Path) -> None:
    launchd.user_agent(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x", ["/bin/echo"])
    ex = FakeExecutor()
    launchd.remove_agent(Ctx(os=MAC, ex=ex), "dev.devboost.x")
    assert ["launchctl", "bootout", f"gui/{UID}/dev.devboost.x"] in ex.calls
    assert not (home / "Library/LaunchAgents/dev.devboost.x.plist").exists()


def test_agent_current_needs_identical_plist_and_loaded(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    args = ["/bin/devboost", "pass", "sync", "--quiet"]
    assert not launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=900)
    launchd.user_agent(ctx, "dev.devboost.x", args, start_interval=900)
    assert launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=900)
    assert not launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=60)
    unloaded = Ctx(os=MAC, ex=FakeExecutor(scripts={"launchctl": Result(113)}))
    assert not launchd.agent_current(unloaded, "dev.devboost.x", args, start_interval=900)


def test_user_agent_keep_alive_throttle_and_log(home: Path) -> None:
    log = home / "Library" / "Logs" / "devboost" / "x.log"
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x", ["/bin/echo"],
        run_at_load=True, keep_alive={"SuccessfulExit": False},
        throttle_interval=60, log_path=log,
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.x.plist").read_bytes())
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 60
    assert data["StandardOutPath"] == str(log)
    assert data["StandardErrorPath"] == str(log)
    assert log.parent.is_dir()


def test_user_agent_keep_alive_true(home: Path) -> None:
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.k", ["/bin/echo"], keep_alive=True
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.k.plist").read_bytes())
    assert data["KeepAlive"] is True


def test_user_agent_without_new_options_has_no_new_keys(home: Path) -> None:
    launchd.user_agent(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.p", ["/bin/echo"])
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.p.plist").read_bytes())
    assert data == {"Label": "dev.devboost.p", "ProgramArguments": ["/bin/echo"]}


def test_pass_sync_style_plist_bytes_are_unchanged(home: Path) -> None:
    """M4-D7: the new kwargs default to None, so an existing agent's bytes stay identical."""
    args = ["/bin/devboost", "pass", "sync", "--quiet"]
    launchd.user_agent(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.pass-sync", args,
                       start_interval=900)
    expected = plistlib.dumps(
        {"Label": "dev.devboost.pass-sync", "ProgramArguments": args, "StartInterval": 900}
    )
    assert (home / "Library/LaunchAgents/dev.devboost.pass-sync.plist").read_bytes() == expected


def test_agent_current_honours_the_new_options(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    log = home / "Library" / "Logs" / "devboost" / "t.log"
    lbl, args = "dev.devboost.t", ["/bin/echo"]
    ka = {"SuccessfulExit": False}
    launchd.user_agent(ctx, lbl, args, keep_alive=ka, throttle_interval=30, log_path=log)
    assert launchd.agent_current(
        ctx, lbl, args, keep_alive=ka, throttle_interval=30, log_path=log
    )
    assert not launchd.agent_current(ctx, lbl, args)
    assert not launchd.agent_current(
        ctx, lbl, args, keep_alive=True, throttle_interval=30, log_path=log
    )
    again = launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), lbl, args,
        keep_alive=ka, throttle_interval=30, log_path=log,
    )
    assert again is False


def test_agent_plist_and_agent_installed(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert launchd.agent_installed(ctx, "dev.devboost.x") is False  # no plist yet
    launchd.user_agent(ctx, "dev.devboost.x", ["/bin/echo"])
    assert launchd.agent_plist("dev.devboost.x") == (
        home / "Library" / "LaunchAgents" / "dev.devboost.x.plist"
    )
    assert launchd.agent_installed(ctx, "dev.devboost.x") is True
    unloaded = Ctx(os=MAC, ex=FakeExecutor(scripts={"launchctl": Result(113)}))
    assert launchd.agent_installed(unloaded, "dev.devboost.x") is False


def test_remove_daemon_bootouts_and_deletes_with_sudo(home: Path) -> None:
    ex = FakeExecutor()
    launchd.remove_daemon(Ctx(os=MAC, ex=ex), "dev.devboost.docker-sock")
    assert ex.calls == [
        ["sudo", "launchctl", "bootout", "system/dev.devboost.docker-sock"],
        ["sudo", "rm", "-f", str(home / "LaunchDaemons" / "dev.devboost.docker-sock.plist")],
    ]
