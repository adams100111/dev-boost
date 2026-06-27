from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.dev_stacks import (
    AndroidSdk,
    Aspire,
    DataServices,
    DevopsTools,
    DotnetLsp,
    DotnetSdk,
    Expo,
    PythonLsp,
    Uv,
    WebRuntimes,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_uv_installs_pinned() -> None:
    ctx = _ctx()
    Uv().install(ctx)
    assert "astral.sh/uv/0.11.23" in ctx.ex.calls[0][2]  # type: ignore[attr-defined]


def test_web_runtimes_pins_node_pnpm_bun() -> None:
    ctx = _ctx()
    WebRuntimes().install(ctx)
    assert ["mise", "use", "-g", "node@22", "pnpm@11.8.0", "bun@1.3.14"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_dotnet_sdk_install_and_verify() -> None:
    ctx = _ctx()
    DotnetSdk().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "dotnet-sdk-10.0"] in ctx.ex.calls  # type: ignore[attr-defined]
    ctx2 = _ctx(scripts={"dotnet": Result(0, stdout="10.0.100 [/usr/lib/...]")})
    assert DotnetSdk().verify(ctx2) is True


def test_aspire_installs_tool() -> None:
    ctx = _ctx()
    Aspire().install(ctx)
    assert ["dotnet", "tool", "install", "-g", "Aspire.Cli"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_dotnet_lsp_installs_csharp_tools() -> None:
    ctx = _ctx()
    DotnetLsp().install(ctx)
    assert ["dotnet", "tool", "install", "-g", "csharp-ls"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_devops_tools_pins_clis() -> None:
    ctx = _ctx()
    DevopsTools().install(ctx)
    flat = " ".join(ctx.ex.calls[0])  # type: ignore[attr-defined]
    assert "opentofu/opentofu@1.11.6" in flat and "derailed/k9s@0.51.0" in flat


def test_python_lsp_seeds_and_pins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    PythonLsp().install(ctx)
    assert ["mise", "use", "-g", "pipx:basedpyright@1.39.8"] in ctx.ex.calls  # type: ignore[attr-defined]
    cfg = tmp_path / ".config" / "fresh" / "config.json"
    assert "basedpyright-langserver" in cfg.read_text(encoding="utf-8")


def test_data_services_verify_reads_bundled_compose() -> None:
    assert DataServices().verify(_ctx()) is True


def test_expo_verify_reads_bundled_template() -> None:
    assert Expo().verify(_ctx()) is True


def test_android_sdk_provisions_jdk_and_sdkmanager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "Android" / "Sdk"))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    assert ["mise", "use", "-g", "java@temurin-17"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert any("sdkmanager" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_android_sdk_renames_nested_cmdline_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate unzip producing cmdline-tools/cmdline-tools/ (nested); verify rename to latest/."""
    sdk = tmp_path / "Android" / "Sdk"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    # pre-create the nested directory that unzip produces
    nested = sdk / "cmdline-tools" / "cmdline-tools" / "bin"
    nested.mkdir(parents=True)
    (nested / "sdkmanager").write_text("#!/bin/sh", encoding="utf-8")
    ctx = _ctx()
    AndroidSdk().install(ctx)
    # The nested dir should have been renamed to latest/
    assert (sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager").exists()
    assert not (sdk / "cmdline-tools" / "cmdline-tools").exists()


def test_android_sdk_writes_profile_d_android(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk = tmp_path / "Android" / "Sdk"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("devboost-android.sh" in " ".join(c) for c in calls)
