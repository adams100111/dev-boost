from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _zed
from devboost.modules.editors import Vscode, Zed, zed_install_steps

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
MAC = OsInfo("macos", "macos", "aarch64")
SCRIPT = Path("/tmp/zed-install.sh")
CURL = [
    "curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o", str(SCRIPT),
    "https://zed.dev/install.sh",
]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@dataclass
class _Downloader(FakeExecutor):
    """FakeExecutor whose `curl -o <file>` really creates <file>, like the real download."""

    downloaded: list[Path] = field(default_factory=list)

    def run(self, argv: Sequence[str], **kw: Any) -> Result:
        res = super().run(argv, **kw)
        if argv[0] == "curl" and res.ok:
            out = Path(argv[argv.index("-o") + 1])
            out.write_text("#!/bin/sh\n", encoding="utf-8")
            self.downloaded.append(out)
        return res


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH])
def test_linux_downloads_the_official_script_then_runs_it(os_info: OsInfo) -> None:
    assert zed_install_steps(os_info, SCRIPT) == [CURL, ["sh", str(SCRIPT)]]


def test_install_has_no_sudo_and_no_pipe_to_shell() -> None:
    for argv in zed_install_steps(FEDORA, SCRIPT):
        assert "sudo" not in argv and "-c" not in argv and "|" not in " ".join(argv)


def test_macos_install_is_z2() -> None:
    with pytest.raises(UnsupportedOS, match="cask"):
        zed_install_steps(MAC, SCRIPT)


def test_install_runs_script_then_seeds_and_guarantees_config() -> None:
    ex = _Downloader()
    Zed().install(Ctx(os=FEDORA, ex=ex))
    assert [c[0] for c in ex.calls] == ["curl", "sh"]
    (script,) = ex.downloaded
    assert ex.calls[1] == ["sh", str(script)]
    assert not script.exists()  # the temp file is removed after the run
    data = json.loads(_zed.settings_path().read_text(encoding="utf-8"))
    assert data["base_keymap"] == "VSCode"
    assert set(data["agent_servers"]) == {"claude-acp", "codex-acp", "pi-acp"}


def test_install_skips_the_script_when_zed_is_present() -> None:
    ex = FakeExecutor(present={"zed"})
    Zed().install(Ctx(os=UBUNTU, ex=ex))
    assert ex.calls == []
    assert _zed.settings_path().exists()


def test_failed_download_is_an_install_error_naming_curl() -> None:
    ex = _Downloader(scripts={"curl": Result(22)})
    with pytest.raises(InstallError) as exc:
        Zed().install(Ctx(os=FEDORA, ex=ex))
    assert exc.value.module == "zed"
    assert exc.value.command.startswith("curl ") and exc.value.code == 22
    assert "zed.dev/install.sh" in exc.value.command
    assert [c[0] for c in ex.calls] == ["curl"]  # the script is never run
    assert not _zed.settings_path().exists()


def test_failed_script_names_module_and_command_and_cleans_up() -> None:
    ex = _Downloader(scripts={"sh": Result(1)})
    with pytest.raises(InstallError) as exc:
        Zed().install(Ctx(os=FEDORA, ex=ex))
    assert exc.value.module == "zed"
    assert exc.value.command.startswith("sh ")
    assert not ex.downloaded[0].exists()


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
