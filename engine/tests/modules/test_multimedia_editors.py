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
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _ubuntu_ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


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


# ---------------------------------------------------------------------------
# VS Code — Fedora
# ---------------------------------------------------------------------------


def test_vscode_imports_key_and_adds_repo() -> None:
    ctx = _ctx()
    Vscode().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "rpm", "--import", "https://packages.microsoft.com/keys/microsoft.asc"] in calls
    assert ["sudo", "tee", "/etc/yum.repos.d/code.repo"] in calls
    assert ["sudo", "dnf", "install", "-y", "code"] in calls


# ---------------------------------------------------------------------------
# VS Code — Ubuntu
# ---------------------------------------------------------------------------


def test_vscode_skips_rpm_import_on_ubuntu() -> None:
    """On Ubuntu, GPG key is handled by Apt.add_repo — no rpm --import call."""
    ctx = _ubuntu_ctx()
    Vscode().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("rpm" in " ".join(c) for c in calls)


def test_vscode_adds_apt_repo_on_ubuntu() -> None:
    """Apt.add_repo writes key + sources.list.d entry + runs apt-get update."""
    ctx = _ubuntu_ctx()
    Vscode().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # Key downloaded via curl
    assert any("curl" in c and "packages.microsoft.com/keys/microsoft.asc" in " ".join(c)
               for c in calls)
    # Key written to keyrings
    assert any("tee" in " ".join(c) and "keyrings" in " ".join(c) for c in calls)
    # sources.list.d entry written
    assert any(
        "tee" in " ".join(c)
        and "sources.list.d" in " ".join(c)
        and "packages-microsoft-com" in " ".join(c)
        for c in calls
    )
    # apt-get update run after adding repo
    assert ["sudo", "apt-get", "update"] in calls


def test_vscode_installs_code_via_apt_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    Vscode().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "code"] in calls


def test_vscode_apt_source_list_line_contains_microsoft_repos() -> None:
    """The AptRepo list_line must reference the Microsoft apt repo URL."""
    from devboost.modules.editors import _VSCODE_SOURCE

    apt_repo = _VSCODE_SOURCE.get(UBUNTU)
    assert apt_repo is not None
    from devboost.model import AptRepo
    assert isinstance(apt_repo, AptRepo)
    assert "packages.microsoft.com/repos/code" in apt_repo.list_line
    assert apt_repo.key_url == "https://packages.microsoft.com/keys/microsoft.asc"


# ---------------------------------------------------------------------------
# Fresh + FreshLsp (cross-distro — both Fedora and Ubuntu)
# ---------------------------------------------------------------------------


def test_fresh_uses_upstream_installer() -> None:
    ctx = _ctx()
    Fresh().install(ctx)
    assert ctx.ex.calls[0][0] == "sh"  # type: ignore[attr-defined]


def test_fresh_installer_works_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
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
