from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.cache import Cache
from devboost.media.config import IsoSpec, MediaConfig
from devboost.media.download import FakeDownloader
from devboost.media.report import FakeReporter
from devboost.media.stages import boot_artifacts, render_kscfg
from devboost.model import Ctx

OS = OsInfo("fedora", "fedora", "x86_64")

# lsblk -P output: /dev/sdb is removable, unmounted — passes validate()
_LSBLK = (
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
)

# lsblk -P -o NAME,MOUNTPOINT /dev/sdb — no mounted children → validate() passes child check
_LSBLK_CHILDREN_CLEAN = 'NAME="sdb" MOUNTPOINT=""\nNAME="sdb1" MOUNTPOINT=""\n'

# Fake path returned by a monkeypatched ensure_ventoy
_FAKE_VENTOY = Path("/fake/ventoy-1.1.16/Ventoy2Disk.sh")


def _make_executor(
    *, lsblk_out: str = _LSBLK, child_out: str = _LSBLK_CHILDREN_CLEAN
) -> FakeExecutor:
    """FakeExecutor handling both lsblk variants: validate() + _find_vtoy_partition()."""
    return FakeExecutor(scripts={"lsblk": Result(0, stdout=lsblk_out + child_out)})


# lsblk -P -o NAME,MOUNTPOINT /dev/sdb — GNOME/udisks2 auto-mounted the stick on plug-in
_LSBLK_CHILDREN_AUTOMOUNTED = (
    'NAME="sdb" MOUNTPOINT=""\nNAME="sdb1" MOUNTPOINT="/run/media/dev/FEDORA-WS-L"\n'
)


class _AutomountedExecutor(FakeExecutor):
    """Models a real auto-mounted stick: lsblk reports sdb1 mounted until `umount` runs.

    The plain FakeExecutor replays one canned lsblk forever, so it cannot express the state
    change an unmount causes — and a validate() that follows the unmount would still see the
    stale mount.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        result = super().run(argv, sudo=sudo, stdin=stdin, env=env)
        if argv and argv[0] == "umount":
            self.scripts["lsblk"] = Result(0, stdout=_LSBLK + _LSBLK_CHILDREN_CLEAN)
        return result


def test_boot_artifacts_unmounts_automounts_before_validating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported failure: GNOME auto-mounts the target, so validate() refused the wipe
    *after* the user had already confirmed it. Once confirmed, clear the auto-mount instead."""
    iso_bytes = b"fedora-iso"
    iso = IsoSpec(
        id="fedora-44",
        url="https://x/f.iso",
        sha256=hashlib.sha256(iso_bytes).hexdigest(),
        edition="Everything",
    )
    cache = Cache(tmp_path / "cache")
    fake_tarball = tmp_path / "devboost-x86_64.tar.gz"
    fake_tarball.write_bytes(b"dummy tarball bytes")
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )
    monkeypatch.setattr(
        "devboost.media.stages.injection_archive_path", lambda arch: fake_tarball
    )

    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("cli",),
        cache_dir=cache.cache_dir,
        assume_yes=True,  # the wipe IS confirmed — so the auto-mount may be cleared
    )
    ex = _AutomountedExecutor(
        scripts={"lsblk": Result(0, stdout=_LSBLK + _LSBLK_CHILDREN_AUTOMOUNTED)}
    )
    ctx = Ctx(os=OS, ex=ex)

    boot_artifacts(
        ctx,
        cfg,
        FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes}),
        cache,
        vtoy_mount=tmp_path / "VTOY",
        reporter=FakeReporter(),
    )

    assert ["sudo", "umount", "/dev/sdb1"] in ex.calls
    # ...and the unmount must precede the Ventoy install, not trail it.
    flat = [" ".join(c) for c in ex.calls]
    umount_at = next(i for i, c in enumerate(flat) if "umount /dev/sdb1" in c)
    ventoy_at = next(i for i, c in enumerate(flat) if "Ventoy2Disk" in c)
    assert umount_at < ventoy_at


def test_boot_artifacts_does_not_unmount_before_the_wipe_is_confirmed(tmp_path: Path) -> None:
    """Consent gates the unmount: no confirmation → touch nothing at all."""
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    cache = Cache(tmp_path / "cache")
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("cli",),
        cache_dir=cache.cache_dir,
        assume_yes=False,
    )
    ex = _make_executor(child_out=_LSBLK_CHILDREN_AUTOMOUNTED)
    with pytest.raises(DeviceError, match="not confirmed"):
        boot_artifacts(
            Ctx(os=OS, ex=ex),
            cfg,
            FakeDownloader(cache, blobs={}),
            cache,
            vtoy_mount=tmp_path / "VTOY",
            reporter=FakeReporter(),
        )
    assert not [c for c in ex.calls if "umount" in c]


def test_render_ventoy_json_default_only_omits_auto_install() -> None:
    import json

    from devboost.media.stages import render_ventoy_json

    data = json.loads(render_ventoy_json(default_iso="fedora-44.iso", autoinstall_iso=None))
    assert data["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"
    assert data["injection"] == [
        {"image": "/ISO/fedora-44.iso", "archive": "/Bootstrap/devboost.tar.gz"}
    ]
    assert "auto_install" not in data


def test_render_ventoy_json_with_autoinstall_binds_both() -> None:
    import json

    from devboost.media.stages import render_ventoy_json

    data = json.loads(
        render_ventoy_json(default_iso="fedora-44.iso", autoinstall_iso="fedora-44-netinst.iso")
    )
    assert data["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"
    assert data["auto_install"] == [
        {"image": "/ISO/fedora-44-netinst.iso", "template": "/Bootstrap/ks.cfg"}
    ]
    # injection lists BOTH ISOs
    images = sorted(e["image"] for e in data["injection"])
    assert images == ["/ISO/fedora-44-netinst.iso", "/ISO/fedora-44.iso"]


def test_render_kscfg_substitutes_profiles() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("cli", "shell"))
    assert "devboost install cli shell" in out and "install full" not in out


def test_boot_artifacts_refuses_wipe_without_assume_yes(tmp_path: Path) -> None:
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={})
    cfg = MediaConfig(
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
        boot_artifacts(ctx, cfg, dl, cache, vtoy_mount=tmp_path / "VTOY", reporter=FakeReporter())
    # Must not have called any ventoy or mount commands
    flat = [" ".join(c) for c in ex.calls]
    assert not any("Ventoy2Disk" in c or "ventoy" in c for c in flat)


def test_boot_artifacts_installs_ventoy_and_stages_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    iso_bytes = b"fedora-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")

    # give the build a netinst auto-install ISO too
    netinst_bytes = b"fedora-netinst"
    netinst_sha = hashlib.sha256(netinst_bytes).hexdigest()
    netinst = IsoSpec(
        id="fedora-44-netinst", url="https://x/n.iso", sha256=netinst_sha, edition="netinst"
    )

    ventoy_bytes = b"ventoy-tarball"
    ventoy_url = "https://github.com/ventoy/Ventoy/releases/download/v1.1.16/ventoy-1.1.16-linux.tar.gz"

    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(
        cache,
        blobs={
            "https://x/f.iso": iso_bytes,
            "https://x/n.iso": netinst_bytes,
            ventoy_url: ventoy_bytes,
        },
    )
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        autoinstall_iso=netinst,
        profiles=("cli",),
        cache_dir=cache.cache_dir,
        assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=_make_executor())

    # Build hermetic fakes for resource_path targets
    ks_template = (
        "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    )
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text(ks_template, encoding="utf-8")
    fake_tarball = tmp_path / "devboost-x86_64.tar.gz"
    fake_tarball.write_bytes(b"dummy tarball bytes")

    def fake_resource_path(*parts: str) -> Path:
        if parts == ("ventoy", "ks.cfg"):
            return fake_ks
        raise KeyError(parts)

    monkeypatch.setattr("devboost.media.stages.resource_path", fake_resource_path)
    monkeypatch.setattr(
        "devboost.media.stages.injection_archive_path", lambda arch: fake_tarball
    )
    # ensure_ventoy: return a fake Ventoy2Disk.sh path (no real extraction needed)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )

    boot_artifacts(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # Should have called sh .../Ventoy2Disk.sh -i /dev/sdb (via sudo)
    assert any(
        "Ventoy2Disk.sh" in " ".join(c) and "-i" in c and "/dev/sdb" in c for c in calls
    )
    assert (vtoy / "Bootstrap" / "ks.cfg").read_text().count("devboost install cli") == 1
    # both ISOs staged
    assert (vtoy / "ISO" / "fedora-44.iso").exists()
    assert (vtoy / "ISO" / "fedora-44-netinst.iso").exists()
    # generated ventoy.json binds both ISOs
    vj = json.loads((vtoy / "ventoy" / "ventoy.json").read_text())
    assert vj["auto_install"][0]["image"] == "/ISO/fedora-44-netinst.iso"
    assert vj["control"][1]["VTOY_DEFAULT_IMAGE"] == "/ISO/fedora-44.iso"


def test_boot_artifacts_stages_secrets_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """age-key.txt is staged alongside secrets.age when secrets_key_path is set."""
    iso_bytes = b"iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="E")

    secrets_file = tmp_path / "secrets.age"
    secrets_file.write_bytes(b"age-encrypted")
    key_file = tmp_path / "age-key.txt"
    key_file.write_text("AGE-SECRET-KEY-1...", encoding="utf-8")

    ventoy_url = "https://github.com/ventoy/Ventoy/releases/download/v1.1.16/ventoy-1.1.16-linux.tar.gz"
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes, ventoy_url: b"vt"})
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=iso,
        profiles=("full",),
        cache_dir=cache.cache_dir,
        assume_yes=True,
        secrets_path=secrets_file,
        secrets_key_path=key_file,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=_make_executor())
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text("install full", encoding="utf-8")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar")
    monkeypatch.setattr("devboost.media.stages.resource_path", lambda *p: fake_ks)
    monkeypatch.setattr("devboost.media.stages.injection_archive_path", lambda arch: fake_tar)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )
    boot_artifacts(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())
    assert (vtoy / "Bootstrap" / "secrets.age").exists()
    assert (vtoy / "Bootstrap" / "age-key.txt").read_text() == "AGE-SECRET-KEY-1..."


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
    from devboost.media.stages import update_stage

    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    ventoy_url = "https://github.com/ventoy/Ventoy/releases/download/v1.1.16/ventoy-1.1.16-linux.tar.gz"
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={ventoy_url: b"vt"})
    cfg = MediaConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=_make_executor())

    ks_template = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full'"
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text(ks_template, encoding="utf-8")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar")

    monkeypatch.setattr(
        "devboost.media.stages.resource_path",
        lambda *p: fake_ks if p == ("ventoy", "ks.cfg") else fake_tar,
    )
    monkeypatch.setattr("devboost.media.stages.injection_archive_path", lambda arch: fake_tar)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )
    update_stage(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    flat = [" ".join(c) for c in calls]
    assert any("Ventoy2Disk.sh" in c and "-u" in c and "/dev/sdb" in c for c in flat)
    assert not any("Ventoy2Disk.sh" in c and "-i" in c for c in flat)  # never wipes
    assert (vtoy / "Bootstrap" / "devboost.tar.gz").exists()
    assert (vtoy / "Bootstrap" / ".devboost-usb.json").exists()
    assert not (vtoy / "ISO" / "fedora-44.iso").exists()  # payload-only by default
    assert dl.fetched == []  # no ISO download (Ventoy tarball is pre-staged in fake blobs
    # but FakeDownloader doesn't record the ventoy URL since it's not fetched in this test
    # because ensure_ventoy is monkeypatched out)


def test_update_stage_refreshes_iso_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from devboost.media.stages import update_stage

    iso_bytes = b"new-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes})
    cfg = MediaConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", refresh_iso=True, assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=_make_executor())
    fake_ks = tmp_path / "ks.cfg"
    fake_ks.write_text("install full", encoding="utf-8")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"
    fake_tar.write_bytes(b"tar")
    monkeypatch.setattr(
        "devboost.media.stages.resource_path",
        lambda *p: fake_ks if p == ("ventoy", "ks.cfg") else fake_tar,
    )
    monkeypatch.setattr("devboost.media.stages.injection_archive_path", lambda arch: fake_tar)
    monkeypatch.setattr(
        "devboost.media.stages.ensure_ventoy", lambda ctx, dl, cache: _FAKE_VENTOY
    )
    update_stage(ctx, cfg, dl, cache, vtoy_mount=vtoy, reporter=FakeReporter())
    assert (vtoy / "ISO" / "fedora-44.iso").read_bytes() == iso_bytes
    assert dl.fetched == ["https://x/f.iso"]


def test_extra_isos_and_installers_are_staged(tmp_path: Path) -> None:
    from devboost.media.config import IsoSpec, MediaConfig
    from devboost.media.stages import extra_isos, installers

    extra = tmp_path / "win.iso"
    extra.write_bytes(b"win")
    inst = tmp_path / "tool.run"
    inst.write_bytes(b"run")
    iso = IsoSpec(id="fedora-44", url="u", sha256="s", edition="E")
    cfg = MediaConfig(
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


def test_mount_lifecycle_recorded_when_no_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In production mode (vtoy_mount=None), stages must call mount + umount + sync."""
    from devboost.media.stages import _mounted_vtoy

    # lsblk output showing sdb1 with LABEL=VTOY
    lsblk_vtoy = 'NAME="sdb" LABEL=""\nNAME="sdb1" LABEL="VTOY"\n'
    ex = FakeExecutor(scripts={"lsblk": Result(0, stdout=lsblk_vtoy)})
    ctx = Ctx(os=OS, ex=ex)

    # Monkeypatch mkdtemp to return a real tmp_path subdir so we can observe it
    mount_dir = tmp_path / "mount"
    mount_dir.mkdir()
    monkeypatch.setattr("devboost.media.stages.mkdtemp", lambda prefix="": str(mount_dir))

    with _mounted_vtoy(ctx, "/dev/sdb") as mnt:
        assert mnt == mount_dir

    flat = [" ".join(c) for c in ex.calls]
    assert any("mount" in c and "sdb1" in c for c in flat)
    assert any("umount" in c for c in flat)
    assert any("sync" in c for c in flat)


def test_mounted_vtoy_yields_override_without_syscalls(tmp_path: Path) -> None:
    """When override is provided, no mount/umount/sync calls are made."""
    from devboost.media.stages import _mounted_vtoy

    ex = FakeExecutor()
    ctx = Ctx(os=OS, ex=ex)
    override = tmp_path / "override"
    override.mkdir()

    with _mounted_vtoy(ctx, "/dev/sdb", override=override) as mnt:
        assert mnt == override

    assert ex.calls == []  # no system calls at all
