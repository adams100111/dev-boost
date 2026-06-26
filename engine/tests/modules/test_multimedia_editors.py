from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import Rpmfusion
from devboost.modules.editors import Fresh, FreshLsp, Vscode
from devboost.modules.mise import Mise
from devboost.modules.multimedia import Codecs, FfmpegFull, Openh264, VaHwaccel

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_ffmpeg_full_swaps_and_requires_rpmfusion() -> None:
    assert Rpmfusion in FfmpegFull.requires
    ctx = _ctx()
    FfmpegFull().install(ctx)
    assert ["sudo", "dnf", "swap", "ffmpeg-free", "ffmpeg", "--allowerasing", "-y"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_codecs_installs_multimedia_group() -> None:
    ctx = _ctx()
    Codecs().install(ctx)
    assert any("@multimedia" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_va_hwaccel_detects_intel() -> None:
    ctx = _ctx(scripts={"lspci": Result(0, stdout="00:02.0 VGA compatible controller: Intel UHD")})
    VaHwaccel().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "intel-media-driver"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_openh264_enables_repo() -> None:
    ctx = _ctx()
    Openh264().install(ctx)
    flat = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("fedora-cisco-openh264.enabled=1" in c for c in flat)
    assert any("mozilla-openh264" in c for c in flat)


def test_vscode_imports_key_and_adds_repo() -> None:
    ctx = _ctx()
    Vscode().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "rpm", "--import", "https://packages.microsoft.com/keys/microsoft.asc"] in calls
    assert ["sudo", "tee", "/etc/yum.repos.d/code.repo"] in calls
    assert ["sudo", "dnf", "install", "-y", "code"] in calls


def test_fresh_uses_upstream_installer() -> None:
    ctx = _ctx()
    Fresh().install(ctx)
    assert ctx.ex.calls[0][0] == "sh"  # type: ignore[attr-defined]


def test_fresh_lsp_seeds_config_and_pins_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert {Fresh, Mise} <= set(FreshLsp.requires)
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    FreshLsp().install(ctx)
    assert ["mise", "use", "-g", "aqua:artempyanykh/marksman@2023-12-09"] in ctx.ex.calls  # type: ignore[attr-defined]
    cfg = tmp_path / ".config" / "fresh" / "config.json"
    assert cfg.exists()
    assert "marksman" in cfg.read_text(encoding="utf-8")
