from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.usb.cache import Cache
from devboost.usb.config import IsoSpec, UsbBuildConfig
from devboost.usb.download import FakeDownloader
from devboost.usb.stages import boot_artifacts, render_kscfg

OS = OsInfo("fedora", "fedora", "x86_64")

# lsblk -P output: /dev/sdb is removable, unmounted — passes validate()
_LSBLK = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
)


def test_render_kscfg_substitutes_profiles() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("cli", "shell"))
    assert "devboost install cli shell" in out and "install full" not in out


def test_boot_artifacts_refuses_wipe_without_assume_yes(tmp_path: Path) -> None:
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={})
    cfg = UsbBuildConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("cli",),
        cache_dir=cache.cache_dir,
        assume_yes=False,
    )
    ex = FakeExecutor()
    ctx = Ctx(os=OS, ex=ex)
    with pytest.raises(DeviceError, match="not confirmed"):
        boot_artifacts(ctx, cfg, dl, vtoy_mount=tmp_path / "VTOY")
    assert not any("ventoy" in " ".join(c) for c in ex.calls)


def test_boot_artifacts_installs_ventoy_and_stages_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso_bytes = b"fedora-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes})
    cfg = UsbBuildConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("cli",),
        cache_dir=cache.cache_dir,
        assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))

    # Build hermetic fakes for resource_path targets
    ks_template = (
        "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    )
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text(ks_template, encoding="utf-8")
    fake_ventoy_json = tmp_path / "ventoy.json"
    fake_ventoy_json.write_bytes(b'{"key": "val"}')
    fake_tarball = tmp_path / "devboost-x86_64.tar.gz"
    fake_tarball.write_bytes(b"dummy tarball bytes")

    def fake_resource_path(*parts: str) -> Path:
        if parts == ("ventoy", "ks.cfg"):
            return fake_ks
        if parts == ("ventoy", "ventoy.json"):
            return fake_ventoy_json
        if parts[0] == "dist":
            return fake_tarball
        raise KeyError(parts)

    monkeypatch.setattr("devboost.usb.stages.resource_path", fake_resource_path)

    boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy)

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["ventoy", "-i", "/dev/sdb"] in calls or ["sudo", "ventoy", "-i", "/dev/sdb"] in calls
    assert (vtoy / "Bootstrap" / "ks.cfg").read_text().count("devboost install cli") == 1
    assert (vtoy / "ISO" / "fedora-44.iso").exists()


def test_render_kscfg_offline_appends_flag() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("full",), offline=True)
    assert "devboost install full --offline" in out


def test_render_kscfg_offline_default_unchanged() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("full",))
    assert "--offline" not in out
    assert "devboost install full" in out


def test_extra_isos_and_installers_are_staged(tmp_path: Path) -> None:
    from devboost.usb.config import IsoSpec, UsbBuildConfig
    from devboost.usb.stages import extra_isos, installers

    extra = tmp_path / "win.iso"
    extra.write_bytes(b"win")
    inst = tmp_path / "tool.run"
    inst.write_bytes(b"run")
    iso = IsoSpec(id="fedora-44", url="u", sha256="s", edition="E")
    cfg = UsbBuildConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        cache_dir=tmp_path,
        extra_isos=(extra,),
        installers=(inst,),
    )
    vtoy = tmp_path / "VTOY"
    (vtoy / "ISO").mkdir(parents=True)
    (vtoy / "Installers").mkdir()
    extra_isos(cfg, vtoy_mount=vtoy)
    installers(cfg, vtoy_mount=vtoy)
    assert (vtoy / "ISO" / "win.iso").exists() and (
        vtoy / "Installers" / "tool.run"
    ).exists()
