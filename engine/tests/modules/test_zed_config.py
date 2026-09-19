from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import _zed
from devboost.modules._lsp import ServerPin, all_pins, read_pins, read_servers

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
