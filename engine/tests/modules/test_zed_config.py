from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import _zed
from devboost.modules._lsp import ServerPin, all_pins, read_pins, read_servers
from devboost.modules.dev_stacks import DotnetLsp, PythonLsp

CTX = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _shim(home: Path, cmd: str) -> Path:
    p = home / ".local" / "share" / "mise" / "shims" / cmd
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    return p


def test_read_pins_carries_args_and_read_servers_is_unchanged() -> None:
    pins = {p.cmd: p for p in read_pins("python-lsp.tsv")}
    assert pins["basedpyright-langserver"].args == ("--stdio",)
    assert pins["ruff"].args == ("server",)
    assert ("python", "basedpyright-langserver", "pipx:basedpyright@1.39.8") in read_servers(
        "python-lsp.tsv"
    )


def test_all_pins_covers_every_fresh_tsv() -> None:
    cmds = {p.cmd for p in all_pins()}
    assert {"marksman", "intelephense", "tofu-ls", "tailwindcss-language-server"} <= cmds


def test_every_mise_row_in_the_zed_map_resolves_from_a_fresh_pin(home: Path) -> None:
    rows = _zed.read_lsp_map()
    assert {r[0] for r in rows} == {
        "basedpyright", "ruff", "tailwindcss-language-server", "intelephense",
        "tofu-ls", "yaml-language-server", "csharp-ls",
    }
    for _, cmd, resolver in rows:
        if resolver == "mise":
            _shim(home, cmd)
    tools = home / ".dotnet" / "tools"
    tools.mkdir(parents=True)
    (tools / "csharp-ls").write_text("", encoding="utf-8")
    out = _zed.lsp_binaries(all_pins(), home)  # raises ValueError if a pin is missing
    assert set(out) == {r[0] for r in rows}


def test_lsp_binary_path_is_the_mise_shim_with_tsv_args(home: Path) -> None:
    shim = _shim(home, "basedpyright-langserver")
    out = _zed.lsp_binaries(all_pins(), home)
    assert out == {"basedpyright": {"binary": {"path": str(shim), "arguments": ["--stdio"]}}}


def test_absent_binaries_are_not_written(home: Path) -> None:
    assert _zed.lsp_binaries(all_pins(), home) == {}


def test_csharp_ls_resolves_from_dotnet_tools(home: Path) -> None:
    tools = home / ".dotnet" / "tools"
    tools.mkdir(parents=True)
    (tools / "csharp-ls").write_text("", encoding="utf-8")
    assert _zed.lsp_binaries(all_pins(), home)["csharp-ls"] == {
        "binary": {"path": str(tools / "csharp-ls"), "arguments": []}
    }


def test_mise_row_without_pin_is_a_loud_error(home: Path) -> None:
    with pytest.raises(ValueError, match="no pin"):
        _zed.lsp_binaries([ServerPin("x", "other", "npm:other@1")], home)


def test_must_have_patch_is_exactly_the_spec_keys(home: Path) -> None:
    _shim(home, "ruff")
    patch = _zed.must_have_patch(all_pins(), home)
    assert set(patch) == {
        "auto_install_extensions", "agent_servers", "languages", "telemetry", "lsp",
    }
    assert patch["languages"] == {
        "CSharp": {"language_servers": ["csharp-ls", "!roslyn", "!omnisharp", "..."]}
    }
    assert set(patch["agent_servers"]) == {"claude-acp", "codex-acp", "pi-acp"}
    ruff_path = str(home / ".local/share/mise/shims/ruff")
    assert patch["lsp"] == {
        "ruff": {"binary": {"path": ruff_path, "arguments": ["server"]}}
    }


def test_ensure_config_seeds_both_files_then_is_a_noop(home: Path) -> None:
    assert _zed.ensure_config(CTX, all_pins()) is False  # seed already satisfies the patch
    assert json.loads(_zed.keymap_path().read_text(encoding="utf-8")) == []
    assert _zed.config_ok(all_pins()) is True


def test_ensure_config_preserves_user_edits_and_restores_must_haves(home: Path) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(
        '{"buffer_font_size": 17, // mine\n "auto_install_extensions": {"rust": true},'
        ' "telemetry": {"metrics": true}}',
        encoding="utf-8",
    )
    assert _zed.config_ok(all_pins()) is False
    assert _zed.ensure_config(CTX, all_pins()) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["buffer_font_size"] == 17
    assert data["auto_install_extensions"]["rust"] is True
    assert data["auto_install_extensions"]["php"] is True
    assert data["telemetry"]["metrics"] is False
    assert "base_keymap" not in data  # the seed is NOT re-applied to a user-owned file
    assert (p.parent / "settings.json.devboost-bak").exists()


def test_ensure_config_picks_up_a_newly_installed_server(home: Path) -> None:
    _zed.ensure_config(CTX, all_pins())
    shim = _shim(home, "intelephense")
    assert _zed.config_ok(all_pins()) is False
    assert _zed.ensure_config(CTX, all_pins()) is True
    data = json.loads(_zed.settings_path().read_text(encoding="utf-8"))
    assert data["lsp"]["intelephense"]["binary"] == {"path": str(shim), "arguments": ["--stdio"]}
    assert "tailwindcss-language-server" in data["lsp"]  # seeded tailwind settings kept


def test_unparseable_settings_is_needs_user(home: Path) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text("{broken", encoding="utf-8")
    with pytest.raises(NeedsUser):
        _zed.ensure_config(CTX, all_pins())
    assert p.read_text(encoding="utf-8") == "{broken"


def test_refresh_after_lsp_is_noop_without_settings(home: Path) -> None:
    _shim(home, "ruff")
    _zed.refresh_after_lsp(CTX, all_pins())
    assert not _zed.settings_path().exists()


def test_refresh_after_lsp_downgrades_needs_user_to_warning(home: Path) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text("{broken", encoding="utf-8")
    _zed.refresh_after_lsp(CTX, all_pins())  # must not raise
    assert p.read_text(encoding="utf-8") == "{broken"


def test_python_lsp_install_wires_zed_when_settings_exist(home: Path) -> None:
    _zed.seed_files()
    # FakeExecutor doesn't run `mise use`; the shim appearing is what a real install does.
    _shim(home, "basedpyright-langserver")
    _shim(home, "ruff")
    PythonLsp().install(CTX)
    data = json.loads(_zed.settings_path().read_text(encoding="utf-8"))
    assert data["lsp"]["basedpyright"]["binary"]["arguments"] == ["--stdio"]
    assert data["lsp"]["ruff"]["binary"]["arguments"] == ["server"]


def test_dotnet_lsp_install_wires_csharp_ls(home: Path) -> None:
    _zed.seed_files()
    tools = home / ".dotnet" / "tools"
    tools.mkdir(parents=True)
    (tools / "csharp-ls").write_text("", encoding="utf-8")
    DotnetLsp().install(CTX)
    data = json.loads(_zed.settings_path().read_text(encoding="utf-8"))
    assert data["lsp"]["csharp-ls"]["binary"]["path"] == str(tools / "csharp-ls")


def test_lsp_install_does_not_create_zed_settings(home: Path) -> None:
    _shim(home, "ruff")
    PythonLsp().install(CTX)
    assert not _zed.settings_path().exists()


# --- I1: Zed is Linux-only (SUPPORTED_FAMILIES) --------------------------------------------

MAC_CTX = Ctx(os=OsInfo("macos", "macos", "aarch64"), ex=FakeExecutor())
_NEEDS_MERGE = '{"buffer_font_size": 17}'  # lacks every must-have key → a merge would write


def test_supported_families_is_the_single_source_for_zed_families() -> None:
    from devboost.modules.editors import Zed

    assert _zed.SUPPORTED_FAMILIES == ("fedora", "debian", "arch")
    assert Zed.families == _zed.SUPPORTED_FAMILIES


@pytest.mark.parametrize("module", [PythonLsp, DotnetLsp])
def test_lsp_hook_does_nothing_on_macos(home: Path, module: type) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(_NEEDS_MERGE, encoding="utf-8")
    _shim(home, "ruff")
    tools = home / ".dotnet" / "tools"
    tools.mkdir(parents=True)
    (tools / "csharp-ls").write_text("", encoding="utf-8")
    module().install(MAC_CTX)
    assert p.read_text(encoding="utf-8") == _NEEDS_MERGE
    assert not (p.parent / "settings.json.devboost-bak").exists()
    assert not _zed.keymap_path().exists()
    assert sorted(x.name for x in p.parent.iterdir()) == ["settings.json"]


def test_ensure_config_does_nothing_off_family(home: Path) -> None:
    assert _zed.ensure_config(MAC_CTX, all_pins()) is False
    assert not _zed.settings_path().parent.exists()


# --- I2: the hook never fails an LSP install ----------------------------------------------


def _warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(log, "warn", seen.append)
    return seen


def test_lsp_install_survives_non_utf8_settings(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    body = b'{"buffer_font": "caf\xe9"}'  # latin-1 é
    p.write_bytes(body)
    _shim(home, "ruff")
    seen = _warnings(monkeypatch)
    PythonLsp().install(CTX)
    assert p.read_bytes() == body
    assert len(seen) == 1 and "telemetry" in seen[0]  # NeedsUser names the keys


def test_lsp_install_survives_settings_path_being_a_directory(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _zed.settings_path().mkdir(parents=True)
    seen = _warnings(monkeypatch)
    DotnetLsp().install(CTX)
    assert _zed.settings_path().is_dir()
    assert len(seen) == 1 and seen[0].startswith("zed: ")


def test_lsp_install_survives_a_permission_error(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(_NEEDS_MERGE, encoding="utf-8")

    def _denied(*_: object) -> None:
        raise PermissionError(13, "Permission denied", str(p))

    monkeypatch.setattr(os, "replace", _denied)
    seen = _warnings(monkeypatch)
    PythonLsp().install(CTX)
    assert p.read_text(encoding="utf-8") == _NEEDS_MERGE
    assert len(seen) == 1 and "Permission denied" in seen[0]
    assert not (p.parent / "settings.json.devboost-tmp").exists()


def test_hook_warning_with_markup_like_text_does_not_raise(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _zed.seed_files()

    def _boom(*_: object) -> bool:
        raise RuntimeError("bad <tag> in </path>")

    monkeypatch.setattr(_zed, "ensure_config", _boom)
    _zed.refresh_after_lsp(CTX, all_pins())  # real log.warn: loguru markup must not raise
