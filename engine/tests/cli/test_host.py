from __future__ import annotations

import time

from devboost.cli import host as plat
from devboost.cli.app import default_profile
from devboost.core.osinfo import OsInfo

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_root_is_refused_on_macos_only() -> None:
    assert plat.invocation_error(MAC, "install", euid=0) is not None
    assert "Homebrew" in (plat.invocation_error(MAC, "install", euid=0) or "")
    assert plat.invocation_error(FEDORA, "install", euid=0) is None


def test_linux_only_commands_refused_on_macos() -> None:
    for cmd in ("installer", "accounts", "brain"):
        msg = plat.invocation_error(MAC, cmd, euid=501)
        assert msg is not None and "Linux-only" in msg
    assert plat.invocation_error(MAC, "install", euid=501) is None
    assert plat.invocation_error(FEDORA, "installer", euid=1000) is None


def test_sudo_keepalive_validates_then_refreshes() -> None:
    seen: list[list[str]] = []

    def _record(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    with plat.SudoKeepalive(run=_record, interval=0.01):
        time.sleep(0.05)
    assert seen[0] == ["sudo", "-v"]
    assert ["sudo", "-n", "-v"] in seen[1:]
    count = len(seen)
    time.sleep(0.03)
    assert len(seen) == count  # thread stopped on exit


def test_keep_awake_waits_on_our_pid() -> None:
    started: list[list[str]] = []
    plat.keep_awake(popen=lambda argv: started.append(argv))
    assert started[0][:3] == ["caffeinate", "-dimsu", "-w"]


def test_mac_session_is_noop_off_macos_and_in_dry_run() -> None:
    with plat.mac_session(FEDORA, dry_run=False):
        pass
    with plat.mac_session(MAC, dry_run=True):
        pass


def test_default_profile_on_macos() -> None:
    assert default_profile(MAC) == "macos"
