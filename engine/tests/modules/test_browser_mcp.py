from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._launchd_jobs import launchd_path
from devboost.modules.browser_mcp import BrowserMcp
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _launcher(home: Path) -> Path:
    p = home / ".local" / "bin" / "browser-mcp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return p


def _plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / "dev.devboost.browser-mcp.plist"


def test_runs_the_dotfiles_launcher_as_a_keep_alive_agent(tmp_path: Path) -> None:
    launcher = _launcher(tmp_path)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    BrowserMcp().install(ctx)
    data = plistlib.loads(_plist_path(tmp_path).read_bytes())
    assert data["ProgramArguments"] == [str(launcher)]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 60
    shims = str(tmp_path / ".local" / "share" / "mise" / "shims")
    assert data["EnvironmentVariables"] == {"PATH": f"{shims}:{launchd_path()}"}
    log = str(tmp_path / "Library" / "Logs" / "devboost" / "browser-mcp.log")
    assert data["StandardOutPath"] == log and data["StandardErrorPath"] == log
    assert BrowserMcp().verify(ctx) is True


def test_verify_notices_a_drifted_or_unloaded_agent(tmp_path: Path) -> None:
    """M4-D7: verify compares the whole plist (agent_current), not just its presence."""
    _launcher(tmp_path)
    BrowserMcp().install(Ctx(os=MAC, ex=FakeExecutor()))
    unloaded = Ctx(os=MAC, ex=RuleExecutor(rules=[(("launchctl", "print"), Result(113))]))
    assert BrowserMcp().verify(unloaded) is False
    plist = _plist_path(tmp_path)
    data = plistlib.loads(plist.read_bytes())
    data["ThrottleInterval"] = 10
    plist.write_bytes(plistlib.dumps(data))
    assert BrowserMcp().verify(Ctx(os=MAC, ex=FakeExecutor())) is False


def test_missing_launcher_points_at_the_dotfiles() -> None:
    with pytest.raises(ConfigError, match="devboost install dotfiles"):
        BrowserMcp().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert BrowserMcp().verify(Ctx(os=MAC, ex=FakeExecutor())) is False


def test_metadata() -> None:
    assert BrowserMcp.families == ("macos",)
    assert BrowserMcp.profiles == ("remote",)
    assert BrowserMcp.gui is True
    assert [c.name for c in BrowserMcp.requires] == ["dotfiles"]


def test_linux_plans_drop_it(tmp_path: Path) -> None:
    plan = build_plan(["browser-mcp"], load(), FEDORA, gpu_marker=tmp_path / "none")
    assert [p.name for p in plan] == []
    mac = build_plan(["browser-mcp"], load(), MAC, gpu_marker=tmp_path / "none")
    assert [(p.name, p.skip_reason) for p in mac] == [("browser-mcp", None)]


def test_it_is_the_macos_answer_itself() -> None:
    """Macos-only with its own install: the catalog contract reads `portable`."""
    assert BrowserMcp.portable is True
    assert BrowserMcp.per_os.macos is None
