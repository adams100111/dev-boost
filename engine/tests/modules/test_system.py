from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import UnsupportedOS
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
    BtrfsAssistant,
    Btrfsmaintenance,
    DnfAutomaticSecurity,
    Earlyoom,
    Fwupd,
    GpuDetect,
    GrubBtrfs,
    ResticBackup,
    Snapper,
    SnapperDnfHook,
    Swapfile,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


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


def test_snapper_caps_retention_after_create_config() -> None:
    """Retention policy is applied so dnf pre/post snapshots can't pile up to ~50 and fill /."""
    ctx = _ctx()
    Snapper().install(ctx)
    assert [
        "sudo", "snapper", "-c", "root", "set-config",
        "TIMELINE_CREATE=no", "NUMBER_CLEANUP=yes",
        "NUMBER_LIMIT=10", "NUMBER_LIMIT_IMPORTANT=5",
    ] in ctx.ex.calls  # type: ignore[attr-defined]


def test_snapper_verify_true_when_policy_applied() -> None:
    out = (
        "Key                    │ Value\n"
        "───────────────────────┼───────\n"
        "TIMELINE_CREATE        │ no\n"
        "NUMBER_LIMIT           │ 10\n"
        "NUMBER_LIMIT_IMPORTANT │ 5\n"
    )
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(scripts={"snapper": Result(0, stdout=out)}))
    assert Snapper().verify(ctx) is True


def test_snapper_verify_false_when_timeline_still_enabled() -> None:
    # stock (uncapped) config: timeline on, keep-50 — verify must reject it.
    out = "TIMELINE_CREATE        │ yes\nNUMBER_LIMIT           │ 50\n"
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(scripts={"snapper": Result(0, stdout=out)}))
    assert Snapper().verify(ctx) is False


def test_snapper_verify_false_when_config_missing() -> None:
    # get-config exits non-zero when the root config doesn't exist yet.
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(scripts={"snapper": Result(1)}))
    assert Snapper().verify(ctx) is False


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


def test_swapfile_btrfs_creates_sizes_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    swap = tmp_path / "swapfile"
    fstab = tmp_path / "fstab"
    monkeypatch.setenv("DEVBOOST_SWAPFILE_PATH", str(swap))
    monkeypatch.setenv("DEVBOOST_FSTAB", str(fstab))
    ctx = _ctx(scripts={
        "free": Result(0, stdout=f"header\nMem: {16 * 1024**3} 0 0\n"),
        "findmnt": Result(0, stdout="btrfs\n"),
    })
    Swapfile().install(ctx)
    assert ["sudo", "btrfs", "filesystem", "mkswapfile",
            "--size", "16g", "--uuid", "clear", str(swap)] in ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "swapon", str(swap)] in ctx.ex.calls  # type: ignore[attr-defined]
    assert fstab.read_text(encoding="utf-8") == f"{swap} none swap defaults 0 0\n"


def test_swapfile_caps_at_32g(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_SWAPFILE_PATH", str(tmp_path / "swapfile"))
    monkeypatch.setenv("DEVBOOST_FSTAB", str(tmp_path / "fstab"))
    ctx = _ctx(scripts={
        "free": Result(0, stdout=f"header\nMem: {64 * 1024**3} 0 0\n"),
        "findmnt": Result(0, stdout="btrfs\n"),
    })
    Swapfile().install(ctx)
    assert any("--size" in c and "32g" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_swapfile_non_btrfs_uses_fallocate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    swap = tmp_path / "swapfile"
    monkeypatch.setenv("DEVBOOST_SWAPFILE_PATH", str(swap))
    monkeypatch.setenv("DEVBOOST_FSTAB", str(tmp_path / "fstab"))
    ctx = _ctx(scripts={
        "free": Result(0, stdout=f"header\nMem: {8 * 1024**3} 0 0\n"),
        "findmnt": Result(0, stdout="ext4\n"),
    })
    Swapfile().install(ctx)
    assert ["sudo", "fallocate", "-l", "8G", str(swap)] in ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "mkswap", str(swap)] in ctx.ex.calls  # type: ignore[attr-defined]


def test_swapfile_verify_true_when_active_and_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    swap = tmp_path / "swapfile"
    fstab = tmp_path / "fstab"
    fstab.write_text(f"{swap} none swap defaults 0 0\n", encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_SWAPFILE_PATH", str(swap))
    monkeypatch.setenv("DEVBOOST_FSTAB", str(fstab))
    ctx = _ctx(scripts={"swapon": Result(0, stdout=f"{swap}\n")})
    assert Swapfile().verify(ctx) is True


def test_swapfile_verify_false_when_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_SWAPFILE_PATH", str(tmp_path / "swapfile"))
    monkeypatch.setenv("DEVBOOST_FSTAB", str(tmp_path / "fstab"))
    ctx = _ctx()  # swapon --show returns empty → not active
    assert Swapfile().verify(ctx) is False


def test_swapfile_is_fedora_only() -> None:
    ctx = Ctx(os=UBUNTU, ex=FakeExecutor())
    with pytest.raises(UnsupportedOS):
        Swapfile().install(ctx)
    assert Swapfile().verify(ctx) is False


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


# ---------------------------------------------------------------------------
# Ubuntu / Fedora-only guards
# ---------------------------------------------------------------------------


def _ubuntu_ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_grub_btrfs_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        GrubBtrfs().install(ctx)


def test_snapper_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Snapper().install(ctx)


def test_snapper_verify_false_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    assert Snapper().verify(ctx) is False


def test_snapper_dnf_hook_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        SnapperDnfHook().install(ctx)


def test_snapper_dnf_hook_verify_false_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    assert SnapperDnfHook().verify(ctx) is False


def test_btrfs_assistant_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        BtrfsAssistant().install(ctx)


def test_btrfs_assistant_verify_false_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    assert BtrfsAssistant().verify(ctx) is False


def test_btrfsmaintenance_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Btrfsmaintenance().install(ctx)


def test_btrfsmaintenance_verify_false_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    assert Btrfsmaintenance().verify(ctx) is False


def test_dnf_automatic_security_raises_unsupported_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        DnfAutomaticSecurity().install(ctx)


# ---------------------------------------------------------------------------
# Earlyoom — cross-distro with OS-aware config path
# ---------------------------------------------------------------------------


def test_earlyoom_uses_debian_default_path_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conf = tmp_path / "earlyoom"
    monkeypatch.setenv("DEVBOOST_EARLYOOM_CONF", str(conf))
    ctx = _ubuntu_ctx()
    Earlyoom().install(ctx)
    assert Earlyoom().verify(ctx) is True
    # Without env override, Ubuntu should use /etc/default/earlyoom
    monkeypatch.delenv("DEVBOOST_EARLYOOM_CONF", raising=False)
    assert Earlyoom()._conf(ctx) == "/etc/default/earlyoom"


def test_earlyoom_env_override_wins_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom-earlyoom"
    monkeypatch.setenv("DEVBOOST_EARLYOOM_CONF", str(custom))
    ctx = _ubuntu_ctx()
    assert Earlyoom()._conf(ctx) == str(custom)


def test_fwupd_installs_on_ubuntu() -> None:
    """fwupd is cross-distro — same package name, same service."""
    ctx = _ubuntu_ctx()
    Fwupd().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "fwupd"] in calls
    assert ["sudo", "systemctl", "enable", "--now", "fwupd.service"] in calls


def test_restic_backup_installs_via_apt_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ubuntu_ctx()
    ResticBackup().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "restic"] in calls


def test_power_profiles_daemon_skips_install_when_tuned_ppd_provides_it() -> None:
    """Fedora 44 ships tuned-ppd, which Provides+Conflicts `ppd-service` — so
    `dnf install power-profiles-daemon` fails on the conflict. When ppd-service is already
    provided, the module must be satisfied and NOT try to install the conflicting package."""
    from devboost.modules.system import PowerProfilesDaemon

    # rpm -q --whatprovides ppd-service returns 0 (tuned-ppd provides it).
    ctx = _ctx(scripts={"rpm": Result(0, stdout="tuned-ppd-2.27.0-1.fc44.noarch")})
    assert PowerProfilesDaemon().verify(ctx) is True
    PowerProfilesDaemon().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert not any("dnf install" in c and "power-profiles-daemon" in c for c in joined)


def test_power_profiles_daemon_installs_when_nothing_provides_ppd_service() -> None:
    """Where ppd-service is not yet provided (rpm -q fails), install normally."""
    from devboost.modules.system import PowerProfilesDaemon

    ctx = _ctx(scripts={"rpm": Result(1)})  # nothing provides ppd-service
    PowerProfilesDaemon().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("dnf install -y power-profiles-daemon" in c for c in joined)
