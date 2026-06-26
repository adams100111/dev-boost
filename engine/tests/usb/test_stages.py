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
from devboost.usb.report import FakeReporter
from devboost.usb.stages import boot_artifacts, render_kscfg

OS = OsInfo("fedora", "fedora", "x86_64")

# lsblk -P output: /dev/sdb is removable, unmounted — passes validate()
_LSBLK = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
)


def test_render_ventoy_json_binds_to_staged_iso_name() -> None:
    from devboost.usb.stages import render_ventoy_json

    tmpl = '{"auto_install": [{"image": "/ISO/__DEVBOOST_ISO__", "template": "/Bootstrap/ks.cfg"}]}'
    out = render_ventoy_json(tmpl, iso_name="fedora-44.iso")
    assert "/ISO/fedora-44.iso" in out
    assert "__DEVBOOST_ISO__" not in out


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
        boot_artifacts(ctx, cfg, dl, vtoy_mount=tmp_path / "VTOY", reporter=FakeReporter())
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
    fake_ventoy_json.write_text(
        '{"auto_install": [{"image": "/ISO/__DEVBOOST_ISO__", "template": "/Bootstrap/ks.cfg"}]}',
        encoding="utf-8",
    )
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

    boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["ventoy", "-i", "/dev/sdb"] in calls or ["sudo", "ventoy", "-i", "/dev/sdb"] in calls
    assert (vtoy / "Bootstrap" / "ks.cfg").read_text().count("devboost install cli") == 1
    assert (vtoy / "ISO" / "fedora-44.iso").exists()
    # ventoy.json bindings track the actual staged ISO filename (not a hardcoded one)
    rendered_json = (vtoy / "ventoy" / "ventoy.json").read_text()
    assert "/ISO/fedora-44.iso" in rendered_json and "__DEVBOOST_ISO__" not in rendered_json


def test_render_kscfg_offline_appends_flag() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("full",), offline=True)
    assert "devboost install full --offline" in out


def test_render_kscfg_offline_default_unchanged() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("full",))
    assert "--offline" not in out
    assert "devboost install full" in out


def test_update_stage_restages_without_wipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.usb.stages import update_stage

    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={})
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))

    ks_template = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full'"
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text(ks_template, encoding="utf-8")
    fake_json = tmp_path / "ventoy.json"
    fake_json.write_bytes(b"{}")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar")

    def fake_resource_path(*parts: str) -> Path:
        return {("ventoy", "ks.cfg"): fake_ks, ("ventoy", "ventoy.json"): fake_json}.get(
            parts, fake_tar
        )

    monkeypatch.setattr("devboost.usb.stages.resource_path", fake_resource_path)
    update_stage(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    flat = [" ".join(c) for c in calls]
    assert any("ventoy -u /dev/sdb" in c for c in flat)
    assert not any("ventoy -i" in c for c in flat)           # never wipes
    assert (vtoy / "Bootstrap" / "devboost.tar.gz").exists()
    assert (vtoy / "Bootstrap" / ".devboost-usb.json").exists()
    assert not (vtoy / "ISO" / "fedora-44.iso").exists()     # payload-only by default
    assert dl.fetched == []                                   # no ISO download


def test_update_stage_refreshes_iso_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from devboost.usb.stages import update_stage

    iso_bytes = b"new-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes})
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", refresh_iso=True, assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text("install full", encoding="utf-8")
    fake_json = tmp_path / "ventoy.json"
    fake_json.write_bytes(b"{}")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar")
    monkeypatch.setattr(
        "devboost.usb.stages.resource_path",
        lambda *p: {("ventoy", "ks.cfg"): fake_ks, ("ventoy", "ventoy.json"): fake_json}.get(
            p, fake_tar
        ),
    )
    update_stage(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())
    assert (vtoy / "ISO" / "fedora-44.iso").read_bytes() == iso_bytes
    assert dl.fetched == ["https://x/f.iso"]


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
