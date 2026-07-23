from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.browser_view import BrowserView


def _ctx(distro: str, family: str) -> Ctx:
    return Ctx(os=OsInfo(distro, family, "x86_64"), ex=FakeExecutor())


def test_browser_view_installs_stack_and_writes_executable_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx("ubuntu", "debian")
    BrowserView().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "xvfb", "x11vnc", "novnc", "websockify"] in calls
    helper = tmp_path / ".local" / "bin" / "browser-view"
    assert helper.exists()
    assert os.access(helper, os.X_OK)
    # the dropped helper must be valid bash
    assert subprocess.run(["bash", "-n", str(helper)]).returncode == 0


def test_browser_view_fedora_package_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx("fedora", "fedora")
    BrowserView().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert [
        "sudo", "dnf", "install", "-y",
        "xorg-x11-server-Xvfb", "x11vnc", "novnc", "python3-websockify",
    ] in calls


def test_browser_view_verify_needs_tools_and_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # tools present but helper not written yet -> False
    ex = FakeExecutor(present={"Xvfb", "x11vnc"})
    assert BrowserView().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)) is False
    # after install (writes helper) -> True
    ctx = Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=FakeExecutor(present={"Xvfb", "x11vnc"}))
    BrowserView().install(ctx)
    assert BrowserView().verify(ctx) is True


def test_browser_view_profiles() -> None:
    assert BrowserView.profiles == ("brain-host",)
