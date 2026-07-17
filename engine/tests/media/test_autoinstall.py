"""Hermetic tests for media/autoinstall.py — render_user_data + autoinstall_for_os dispatch."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.autoinstall import (
    EMPTY_META_DATA,
    autoinstall_for_os,
    render_user_data,
)
from devboost.media.cache import Cache
from devboost.media.config import IsoSpec, MediaConfig
from devboost.media.download import FakeDownloader
from devboost.media.report import FakeReporter
from devboost.media.stages import boot_artifacts, render_ventoy_json
from devboost.model import Ctx

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FEDORA_OS = OsInfo(distro="fedora", family="fedora", arch="x86_64")
UBUNTU_OS = OsInfo(distro="ubuntu", family="debian", arch="x86_64")
ARCH_OS = OsInfo(distro="arch", family="arch", arch="x86_64")

_LIVE_ISO = IsoSpec(
    id="ubuntu-24-04", url="https://x/ubuntu.iso", sha256="a" * 64, edition="desktop"
)
_NETINST_ISO = IsoSpec(
    id="fedora-44-netinst",
    url="https://x/fedora-netinst.iso",
    sha256="b" * 64,
    edition="netinst",
)
_FEDORA_ISO = IsoSpec(
    id="fedora-44", url="https://x/fedora.iso", sha256="c" * 64, edition="Everything"
)
_FAKE_VENTOY = Path("/fake/ventoy-1.1.16/Ventoy2Disk.sh")

# Ventoy2Disk.sh exits 0 regardless; its "successfully finished" line is the real signal.
_VENTOY_OK = "Install Ventoy to /dev/sdb successfully finished."

_LSBLK = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
    # Post-install children: a VTOY partition exists (the install-landed check reads LABEL)
    # and nothing is mounted (validate() reads MOUNTPOINT).
    'NAME="sdb" MOUNTPOINT=""\nNAME="sdb1" LABEL="Ventoy" MOUNTPOINT=""\n'
)


def _ubuntu_cfg(cache_dir: Path) -> MediaConfig:
    return MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=_LIVE_ISO,
        profiles=("full",),
        cache_dir=cache_dir,
        os_family="debian",
    )


def _fedora_cfg(cache_dir: Path) -> MediaConfig:
    return MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=_FEDORA_ISO,
        autoinstall_iso=_NETINST_ISO,
        profiles=("full",),
        cache_dir=cache_dir,
        os_family="fedora",
    )


# ---------------------------------------------------------------------------
# render_user_data
# ---------------------------------------------------------------------------


def test_render_user_data_has_cloud_config_header() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert out.startswith("#cloud-config")


def test_render_user_data_has_version_1() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "version: 1" in out


def test_render_user_data_late_commands_copy_binary() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "/target/opt/dev-boost" in out
    assert "devboost" in out


def test_render_user_data_late_commands_copy_secrets() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "secrets.age" in out
    assert "age-key.txt" in out


def test_render_user_data_late_commands_enable_firstboot_service() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "devboost-firstboot.service" in out
    assert "systemctl enable devboost-firstboot.service" in out


def test_render_user_data_late_commands_install_cloud_init() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "apt-get install" in out
    assert "cloud-init" in out


def test_render_user_data_embeds_install_profiles() -> None:
    out = render_user_data(("cli", "shell"), arch="x86_64")
    assert "install cli shell" in out


def test_render_user_data_full_profiles_present() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "install full" in out


def test_render_user_data_curtin_in_target_enable() -> None:
    out = render_user_data(("full",), arch="x86_64")
    assert "curtin in-target -- systemctl enable devboost-firstboot.service" in out


def test_render_user_data_arch_in_comment() -> None:
    out = render_user_data(("full",), arch="aarch64")
    assert "aarch64" in out


def test_empty_meta_data_is_empty_string() -> None:
    assert EMPTY_META_DATA == ""


# ---------------------------------------------------------------------------
# autoinstall_for_os dispatch
# ---------------------------------------------------------------------------


def test_autoinstall_for_os_fedora_returns_plan(tmp_path: Path) -> None:
    cfg = _fedora_cfg(tmp_path)
    plan = autoinstall_for_os(
        FEDORA_OS,
        cfg,
        ks_template="ExecStart=/opt/dev-boost/devboost install full",
    )
    assert plan is not None
    assert plan.boot_iso == _NETINST_ISO
    assert plan.template_path == "/Bootstrap/ks.cfg"
    assert "ks.cfg" in plan.files


def test_autoinstall_for_os_fedora_ks_content_has_profiles(tmp_path: Path) -> None:
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=_FEDORA_ISO,
        autoinstall_iso=_NETINST_ISO,
        profiles=("cli", "shell"),
        cache_dir=tmp_path,
        os_family="fedora",
    )
    plan = autoinstall_for_os(
        FEDORA_OS,
        cfg,
        ks_template="ExecStart=/opt/dev-boost/devboost install full",
    )
    assert plan is not None
    assert "devboost install cli shell" in plan.files["ks.cfg"]


def test_autoinstall_for_os_fedora_no_netinst_returns_none(tmp_path: Path) -> None:
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=_FEDORA_ISO,
        profiles=("full",),
        cache_dir=tmp_path,
        os_family="fedora",
    )
    assert autoinstall_for_os(FEDORA_OS, cfg, ks_template="tmpl") is None


def test_autoinstall_for_os_debian_returns_plan(tmp_path: Path) -> None:
    cfg = _ubuntu_cfg(tmp_path)
    plan = autoinstall_for_os(UBUNTU_OS, cfg)
    assert plan is not None
    assert plan.boot_iso == _LIVE_ISO
    assert plan.template_path == "/Bootstrap/user-data"
    assert "user-data" in plan.files
    assert "meta-data" in plan.files


def test_autoinstall_for_os_debian_user_data_has_cloud_config(tmp_path: Path) -> None:
    plan = autoinstall_for_os(UBUNTU_OS, _ubuntu_cfg(tmp_path))
    assert plan is not None
    assert plan.files["user-data"].startswith("#cloud-config")


def test_autoinstall_for_os_debian_user_data_has_version_1(tmp_path: Path) -> None:
    plan = autoinstall_for_os(UBUNTU_OS, _ubuntu_cfg(tmp_path))
    assert plan is not None
    assert "version: 1" in plan.files["user-data"]


def test_autoinstall_for_os_debian_meta_data_is_empty(tmp_path: Path) -> None:
    plan = autoinstall_for_os(UBUNTU_OS, _ubuntu_cfg(tmp_path))
    assert plan is not None
    assert plan.files["meta-data"] == ""


def test_autoinstall_for_os_unknown_family_returns_none(tmp_path: Path) -> None:
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=_LIVE_ISO,
        profiles=("full",),
        cache_dir=tmp_path,
    )
    assert autoinstall_for_os(ARCH_OS, cfg) is None


# ---------------------------------------------------------------------------
# render_ventoy_json — Ubuntu dispatch (live ISO + user-data template)
# ---------------------------------------------------------------------------


def test_render_ventoy_json_ubuntu_binds_live_iso_and_user_data() -> None:
    data = json.loads(
        render_ventoy_json(
            default_iso="ubuntu-24-04.iso",
            autoinstall_iso="ubuntu-24-04.iso",
            auto_install_template="/Bootstrap/user-data",
        )
    )
    assert data["auto_install"] == [
        {"image": "/ISO/ubuntu-24-04.iso", "template": "/Bootstrap/user-data"}
    ]
    assert data["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/ubuntu-24-04.iso"


def test_render_ventoy_json_ubuntu_no_duplicate_injection() -> None:
    """When autoinstall_iso == default_iso (Ubuntu), injection must contain exactly one entry."""
    data = json.loads(
        render_ventoy_json(
            default_iso="ubuntu-24-04.iso",
            autoinstall_iso="ubuntu-24-04.iso",
            auto_install_template="/Bootstrap/user-data",
        )
    )
    assert len(data["injection"]) == 1
    assert data["injection"][0]["image"] == "/ISO/ubuntu-24-04.iso"


def test_render_ventoy_json_fedora_default_template_unchanged() -> None:
    """Fedora path: template defaults to /Bootstrap/ks.cfg without explicit arg."""
    data = json.loads(
        render_ventoy_json(default_iso="fedora-44.iso", autoinstall_iso="fedora-44-netinst.iso")
    )
    assert data["auto_install"] == [
        {"image": "/ISO/fedora-44-netinst.iso", "template": "/Bootstrap/ks.cfg"}
    ]
    # Fedora: both ISOs in injection
    images = sorted(e["image"] for e in data["injection"])
    assert images == ["/ISO/fedora-44-netinst.iso", "/ISO/fedora-44.iso"]


# ---------------------------------------------------------------------------
# boot_artifacts — Ubuntu staging integration (hermetic)
# ---------------------------------------------------------------------------


def test_boot_artifacts_ubuntu_stages_user_data_and_meta_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso_bytes = b"ubuntu-iso-content"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="ubuntu-24-04", url="https://x/ubuntu.iso", sha256=sha, edition="desktop")

    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/ubuntu.iso": iso_bytes})
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("full",),
        cache_dir=cache.cache_dir,
        assume_yes=True,
        os_family="debian",
    )
    vtoy = tmp_path / "VTOY"
    ex = FakeExecutor(
        scripts={"lsblk": Result(0, stdout=_LSBLK), "sh": Result(0, stdout=_VENTOY_OK)}
    )
    ctx = Ctx(os=UBUNTU_OS, ex=ex)

    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar-bytes")

    monkeypatch.setattr("devboost.media.stages.injection_archive_path", lambda arch: fake_tar)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )

    boot_artifacts(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())

    # user-data and meta-data staged
    ud_path = vtoy / "Bootstrap" / "user-data"
    md_path = vtoy / "Bootstrap" / "meta-data"
    assert ud_path.exists(), "user-data not staged"
    assert md_path.exists(), "meta-data not staged"
    ud = ud_path.read_text()
    assert ud.startswith("#cloud-config")
    assert "version: 1" in ud
    assert "devboost-firstboot.service" in ud
    assert md_path.read_text() == ""

    # No ks.cfg for Ubuntu
    assert not (vtoy / "Bootstrap" / "ks.cfg").exists()

    # Live ISO staged
    assert (vtoy / "ISO" / "ubuntu-24-04.iso").exists()

    # ventoy.json binds live ISO + user-data
    vj = json.loads((vtoy / "ventoy" / "ventoy.json").read_text())
    assert vj["auto_install"][0]["image"] == "/ISO/ubuntu-24-04.iso"
    assert vj["auto_install"][0]["template"] == "/Bootstrap/user-data"
    assert vj["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/ubuntu-24-04.iso"

    # Only one injection entry (live ISO; no separate netinst)
    assert len(vj["injection"]) == 1


def test_boot_artifacts_ubuntu_no_netinst_iso_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_stage_autoinstall_iso must be a no-op for Ubuntu (no separate netinst to fetch)."""
    iso_bytes = b"ubuntu"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="ubuntu-24-04", url="https://x/ubuntu.iso", sha256=sha, edition="desktop")

    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/ubuntu.iso": iso_bytes})
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("full",),
        cache_dir=cache.cache_dir,
        assume_yes=True,
        os_family="debian",
    )
    vtoy = tmp_path / "VTOY"
    ex = FakeExecutor(
        scripts={"lsblk": Result(0, stdout=_LSBLK), "sh": Result(0, stdout=_VENTOY_OK)}
    )
    ctx = Ctx(os=UBUNTU_OS, ex=ex)

    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"t")

    monkeypatch.setattr("devboost.media.stages.injection_archive_path", lambda arch: fake_tar)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )

    boot_artifacts(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())

    # The only ISO on the USB is the live ISO itself (no *-netinst.iso)
    iso_names = [p.name for p in (vtoy / "ISO").iterdir()]
    assert iso_names == ["ubuntu-24-04.iso"]
