from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._launchd_jobs import launchd_path
from devboost.modules.browser_mcp import BrowserMcp
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO = Path(__file__).resolve().parents[3]


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
    log = str(tmp_path / "Library" / "Logs" / "devboost" / "browser-mcp.log")
    assert data["EnvironmentVariables"] == {
        "PATH": f"{shims}:{launchd_path()}",
        "PLAYWRIGHT_MCP_VERSION": "0.0.82",
        "BROWSER_MCP_LOG": log,  # the launcher caps it (final review M7)
    }
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
    assert BrowserMcp.families == ()  # macOS LaunchAgent and the Linux systemd unit
    assert BrowserMcp.profiles == ()  # opt-in: `devboost install browser-mcp` (C-M4-SEC2)
    assert BrowserMcp.gui is True
    assert [c.name for c in BrowserMcp.requires] == ["dotfiles"]


def test_no_profile_installs_it() -> None:
    """C-M4-SEC2: port 8931 runs code as you, so no profile — default or not — pulls it in."""
    mods = load()
    profiles = load_profiles(REPO / "profiles.toml")
    for name in profiles:
        assert "browser-mcp" not in expand([name], profiles, mods), name


def test_both_oses_plan_it_by_name(tmp_path: Path) -> None:
    for os_ in (FEDORA, MAC):
        plan = build_plan(["browser-mcp"], load(), os_, gpu_marker=tmp_path / "none")
        assert ("browser-mcp", None) in [(p.name, p.skip_reason) for p in plan]


def test_macos_has_its_own_strategy() -> None:
    assert BrowserMcp.per_os.macos is not None


def test_install_prints_the_acl_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _launcher(tmp_path)
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    BrowserMcp().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert any("tcp:8931" in w and "ACL" in w for w in warned)


# ── Linux: the module, never the dotfiles alone, enables the unit (C-M4-SEC2) ──────────────
def _unit(home: Path) -> Path:
    p = home / ".config" / "systemd" / "user" / "browser-mcp.service"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[Unit]\n", encoding="utf-8")
    return p


def test_linux_install_enables_the_dotfiles_unit(tmp_path: Path) -> None:
    _launcher(tmp_path)
    _unit(tmp_path)
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    BrowserMcp().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["systemctl", "--user", "daemon-reload"] in calls
    assert ["systemctl", "--user", "enable", "--now", "browser-mcp.service"] in calls
    assert not any(c[0] == "sudo" for c in calls)
    assert not (tmp_path / "Library").exists()


def test_linux_verify_is_the_enabled_unit(tmp_path: Path) -> None:
    _launcher(tmp_path)
    _unit(tmp_path)
    assert BrowserMcp().verify(Ctx(os=FEDORA, ex=FakeExecutor())) is True
    off = Ctx(os=FEDORA, ex=RuleExecutor(rules=[(("is-enabled",), Result(1))]))
    assert BrowserMcp().verify(off) is False


def test_linux_without_the_unit_points_at_the_dotfiles(tmp_path: Path) -> None:
    _launcher(tmp_path)
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    with pytest.raises(ConfigError, match="devboost install dotfiles"):
        BrowserMcp().install(ctx)
    assert BrowserMcp().verify(ctx) is False


def test_the_dotfiles_no_longer_enable_the_unit() -> None:
    wants = REPO / "dotfiles" / "dot_config" / "systemd" / "user" / "default.target.wants"
    assert not (wants.exists() and list(wants.glob("*browser-mcp*")))
    unit = REPO / "dotfiles" / "dot_config" / "systemd" / "user" / "browser-mcp.service"
    assert unit.is_file()  # the unit itself still ships, inert until the module enables it
