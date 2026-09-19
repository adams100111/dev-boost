from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _zed
from devboost.modules.editors import Vscode, Zed, zed_install_argv

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
MAC = OsInfo("macos", "macos", "aarch64")
ARGV = ["sh", "-c", "curl -fsSL https://zed.dev/install.sh | sh"]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH])
def test_linux_uses_the_official_user_local_script(os_info: OsInfo) -> None:
    assert zed_install_argv(os_info) == ARGV


def test_macos_install_is_z2() -> None:
    with pytest.raises(UnsupportedOS, match="cask"):
        zed_install_argv(MAC)


def test_install_runs_script_then_seeds_and_guarantees_config() -> None:
    ex = FakeExecutor()
    Zed().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == [ARGV]
    data = json.loads(_zed.settings_path().read_text(encoding="utf-8"))
    assert data["base_keymap"] == "VSCode"
    assert set(data["agent_servers"]) == {"claude-acp", "codex-acp", "pi-acp"}


def test_install_skips_the_script_when_zed_is_present() -> None:
    ex = FakeExecutor(present={"zed"})
    Zed().install(Ctx(os=UBUNTU, ex=ex))
    assert ex.calls == []
    assert _zed.settings_path().exists()


def test_failed_script_names_module_and_command() -> None:
    ex = FakeExecutor(scripts={"sh": Result(1)})
    with pytest.raises(InstallError) as exc:
        Zed().install(Ctx(os=FEDORA, ex=ex))
    assert exc.value.module == "zed"
    assert "zed.dev/install.sh" in exc.value.command


def test_verify_needs_binary_and_must_have_keys(tmp_path: Path) -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(present={"zed"}))
    assert Zed().verify(ctx) is False  # no settings yet
    Zed().install(ctx)
    assert Zed().verify(ctx) is True
    p = _zed.settings_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    del data["agent_servers"]["pi-acp"]
    p.write_text(json.dumps(data), encoding="utf-8")
    assert Zed().verify(ctx) is False  # a removed must-have is repaired next run


def test_verify_accepts_the_user_local_symlink_off_path(tmp_path: Path) -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())  # `which` sees nothing (PATH not refreshed)
    Zed().install(ctx)
    link = tmp_path / ".local" / "bin" / "zed"
    link.parent.mkdir(parents=True)
    link.write_text("", encoding="utf-8")
    assert Zed().verify(ctx) is True


def test_zed_is_gui_and_dropped_on_macos_until_z2() -> None:
    modules = load()
    assert Zed.gui is True
    assert build_plan(["zed"], modules, MAC) == []
    headless = OsInfo("fedora", "fedora", "x86_64", headless=True)
    assert build_plan(["zed"], modules, headless)[0].skip_reason == "headless"


def test_vscode_is_opt_in() -> None:
    assert Vscode.profiles == ("optional-editors",)
    assert Vscode.category == "optional-editors"
