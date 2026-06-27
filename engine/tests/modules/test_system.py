from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.registry import load, validate_profiles
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import gpu
from devboost.model import Ctx
from devboost.modules.base import Rpmfusion
from devboost.modules.hardware import NvidiaAkmod, NvidiaContainerToolkit
from devboost.modules.optional import Neovim, Pass
from devboost.modules.system import (
    DnfAutomaticSecurity,
    Earlyoom,
    Fwupd,
    GpuDetect,
    ResticBackup,
    Snapper,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_system_service_installs_and_enables() -> None:
    ctx = _ctx()
    Fwupd().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "fwupd"] in calls
    assert ["sudo", "systemctl", "enable", "--now", "fwupd.service"] in calls


def test_snapper_creates_root_config() -> None:
    ctx = _ctx()
    Snapper().install(ctx)
    assert ["sudo", "snapper", "-c", "root", "create-config", "/"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_dnf_automatic_security_sets_upgrade_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = tmp_path / "automatic.conf"
    monkeypatch.setenv("DEVBOOST_DNF_AUTOMATIC_CONF", str(conf))
    ctx = _ctx()
    DnfAutomaticSecurity().install(ctx)
    assert DnfAutomaticSecurity().verify(ctx) is True


def test_gpu_primitive_detects_nvidia() -> None:
    out = "01:00.0 VGA compatible controller: NVIDIA GP104"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=out)})
    g = gpu.detect(ctx)
    assert g.nvidia and not g.intel


def test_gpu_detect_writes_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    out = "00:02.0 VGA compatible controller: Intel UHD"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=out)})
    GpuDetect().install(ctx)
    assert GpuDetect().verify(ctx) is True
    text = (tmp_path / "state" / "devboost" / "gpu-vendor").read_text(encoding="utf-8")
    assert "intel" in text
    # one vendor per line — no comma-separated format
    assert "," not in text


def test_gpu_detect_nvidia_one_per_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    out = "01:00.0 VGA compatible controller: NVIDIA GP104 [GeForce GTX 1080]"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=out)})
    GpuDetect().install(ctx)
    text = (tmp_path / "state" / "devboost" / "gpu-vendor").read_text(encoding="utf-8")
    assert "nvidia" in text
    assert "," not in text


def test_restic_backup_writes_units_enables_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx(present={"restic"})
    ResticBackup().install(ctx)
    d = tmp_path / ".config" / "systemd" / "user"
    assert (d / "restic-backup.service").exists()
    assert (d / "restic-backup.timer").exists()
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["systemctl", "--user", "enable", "--now", "restic-backup.timer"] in calls


def test_restic_backup_verify_checks_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # verify should be False when timer unit files are absent
    ctx = _ctx()
    assert ResticBackup().verify(ctx) is False


def test_earlyoom_uses_fedora_sysconfig_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = tmp_path / "earlyoom"
    monkeypatch.setenv("DEVBOOST_EARLYOOM_CONF", str(conf))
    ctx = _ctx()
    Earlyoom().install(ctx)
    assert Earlyoom().verify(ctx) is True
    # Default path without env override is Fedora sysconfig, not Debian default
    monkeypatch.delenv("DEVBOOST_EARLYOOM_CONF", raising=False)
    assert Earlyoom()._conf() == "/etc/sysconfig/earlyoom"


def test_nvidia_akmod_requires_rpmfusion_and_installs() -> None:
    assert Rpmfusion in NvidiaAkmod.requires
    ctx = _ctx()
    NvidiaAkmod().install(ctx)
    want = ["sudo", "dnf", "install", "-y", "akmod-nvidia", "xorg-x11-drv-nvidia-cuda"]
    assert want in ctx.ex.calls  # type: ignore[attr-defined]


def test_nvidia_container_toolkit_configures_runtime() -> None:
    ctx = _ctx()
    NvidiaContainerToolkit().install(ctx)
    assert ["sudo", "nvidia-ctk", "runtime", "configure", "--runtime=docker"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_optional_and_security_install() -> None:
    ctx = _ctx()
    Neovim().install(ctx)
    Pass().install(ctx)
    flat = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("neovim" in c for c in flat) and any(c.endswith("pass") for c in flat)


def test_full_catalog_loads_and_all_profiles_validate() -> None:
    import tomllib

    modules = load()
    data = tomllib.loads(settings.profiles_path.read_text(encoding="utf-8"))
    validate_profiles(modules, set(data["profiles"]))
    # the whole production catalog is registered
    assert len(modules) >= 70
