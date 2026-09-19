"""The Claude notify hook: a native notification on macOS, ntfy wherever it is set."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = (Path(__file__).resolve().parents[3] / "dotfiles" / "private_dot_claude" / "hooks"
        / "executable_notify.sh")
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def _run(tmp_path: Path, uname: str, cwd: Path) -> Path:
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    log = tmp_path / "osascript.log"
    for name, body in (
        ("uname", f"echo {uname}"),
        ("osascript", f'printf "%s\\n" "$@" > "{log}"\ncat >> "{log}"'),
    ):
        exe = fake / name
        exe.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        exe.chmod(0o755)
    subprocess.run(
        ["bash", str(HOOK), "done"],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)},
        cwd=cwd, check=True, timeout=10,
    )
    return log


def test_macos_shows_a_native_notification_without_ntfy(tmp_path: Path) -> None:
    text = _run(tmp_path, "Darwin", tmp_path).read_text(encoding="utf-8")
    assert "Claude finished" in text
    assert f"cwd: {tmp_path}" in text
    assert "display notification (item 2 of argv) with title (item 1 of argv)" in text


def test_a_quote_in_the_path_stays_data(tmp_path: Path) -> None:
    odd = tmp_path / 'it"s'
    odd.mkdir()
    text = _run(tmp_path, "Darwin", odd).read_text(encoding="utf-8")
    assert f"cwd: {odd}" in text  # passed as an argument, never spliced into the script


def test_linux_has_no_native_notification(tmp_path: Path) -> None:
    assert not _run(tmp_path, "Linux", tmp_path).exists()


def test_hook_is_valid_bash() -> None:
    assert subprocess.run(["bash", "-n", str(HOOK)], check=False).returncode == 0
