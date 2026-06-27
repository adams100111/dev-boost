"""Builder stages: install Ventoy + lay out the USB; optional extras."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

from devboost import __version__
from devboost.core.errors import DeviceError, VentoyError
from devboost.exec.resources import injection_archive_path, resource_path
from devboost.media.cache import Cache
from devboost.media.config import MediaConfig
from devboost.media.devices import validate
from devboost.media.download import Downloader
from devboost.media.marker import Marker, write_marker
from devboost.media.report import Reporter
from devboost.media.ventoy import ensure_ventoy
from devboost.model import Ctx

_PAIR = re.compile(r'(\w+)="([^"]*)"')


def render_kscfg(
    template: str, profiles: tuple[str, ...], *, offline: bool = False
) -> str:
    install_cmd = "devboost install " + " ".join(profiles)
    if offline:
        install_cmd += " --offline"
    return template.replace("devboost install full", install_cmd)


def render_ventoy_json(*, default_iso: str, autoinstall_iso: str | None) -> str:
    """Generate ventoy.json: default boot + injection on the Live media; auto_install on netinst.

    ``default_iso``/``autoinstall_iso`` are bare filenames (e.g. ``fedora-44.iso``). The
    ``auto_install`` block is emitted only when an autoinstall ISO is present; injection covers
    every staged ISO so the dev-boost binary is available on whichever path boots.
    """
    injection: list[dict[str, str]] = [
        {"image": f"/ISO/{default_iso}", "archive": "/Bootstrap/devboost.tar.gz"}
    ]
    data: dict[str, list[dict[str, str]]] = {
        "control": [
            {"VTOY_MENU_TIMEOUT": "10"},
            {"VTOY_DEFAULT_IMAGE": f"/ISO/{default_iso}"},
        ],
        "injection": injection,
    }
    if autoinstall_iso is not None:
        injection.append(
            {"image": f"/ISO/{autoinstall_iso}", "archive": "/Bootstrap/devboost.tar.gz"}
        )
        data["auto_install"] = [
            {"image": f"/ISO/{autoinstall_iso}", "template": "/Bootstrap/ks.cfg"}
        ]
    return json.dumps(data, indent=2)


def _find_vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """Return the /dev path of the child partition labelled VTOY, or None."""
    out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,LABEL", device]).stdout
    for line in out.splitlines():
        fields = dict(_PAIR.findall(line))
        if fields.get("LABEL") == "VTOY":
            name = fields.get("NAME", "")
            if not name:
                return None
            return name if name.startswith("/dev/") else f"/dev/{name}"
    return None


@contextmanager
def _mounted_vtoy(
    ctx: Ctx, device: str, *, override: Path | None = None
) -> Iterator[Path]:
    """Discover the VTOY partition, mount it read-write, yield the mountpoint, umount+sync.

    When *override* is provided (tests / callers that already have a mount) it is yielded
    directly without any system calls.
    """
    if override is not None:
        yield override
        return

    part = _find_vtoy_partition(ctx, device)
    if part is None:
        raise VentoyError(
            f"VTOY partition not found on {device} after Ventoy install — "
            "the Ventoy2Disk.sh invocation may have failed silently"
        )
    mnt = Path(mkdtemp(prefix="devboost-build-"))
    try:
        if ctx.ex.run(["mount", part, str(mnt)], sudo=True).code != 0:
            raise VentoyError(f"could not mount VTOY partition {part} on {mnt}")
        try:
            yield mnt
        finally:
            ctx.ex.run(["umount", str(mnt)], sudo=True)
            ctx.ex.run(["sync"], sudo=True)
    finally:
        with suppress(OSError):
            mnt.rmdir()


def _stage_payload(cfg: MediaConfig, *, vtoy_mount: Path, reporter: Reporter) -> None:
    """Lay out ventoy.json + ks.cfg + injection archive + secrets + marker (no wipe, no ISO)."""
    boot = vtoy_mount / "Bootstrap"
    for d in ("ISO", "Bootstrap", "Installers", "ventoy"):
        (vtoy_mount / d).mkdir(parents=True, exist_ok=True)
    ai_name = f"{cfg.autoinstall_iso.id}.iso" if cfg.autoinstall_iso is not None else None
    (vtoy_mount / "ventoy" / "ventoy.json").write_text(
        render_ventoy_json(default_iso=f"{cfg.iso.id}.iso", autoinstall_iso=ai_name),
        encoding="utf-8",
    )
    kscfg = resource_path("ventoy", "ks.cfg").read_text(encoding="utf-8")
    (boot / "ks.cfg").write_text(
        render_kscfg(kscfg, cfg.profiles, offline=cfg.offline_mirror), encoding="utf-8"
    )
    # Resolve the injection tarball correctly in both source and frozen-binary mode.
    tarball = injection_archive_path(cfg.arch)
    if not tarball.exists():
        raise VentoyError(
            f"injection archive missing: {tarball} — "
            "run scripts/build-bundle.sh (source) or ship the .tar.gz alongside the binary"
        )
    shutil.copyfile(tarball, boot / "devboost.tar.gz")
    if cfg.secrets_path is not None:
        shutil.copyfile(cfg.secrets_path, boot / "secrets.age")
    if cfg.secrets_key_path is not None:
        shutil.copyfile(cfg.secrets_key_path, boot / "age-key.txt")
    write_marker(
        vtoy_mount,
        Marker(
            version=__version__,
            os_id=cfg.iso.id,
            arch=cfg.arch,
            built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    reporter.step(f"Staged dev-boost payload ({cfg.iso.id}, {cfg.arch})")


def _stage_autoinstall_iso(
    cfg: MediaConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if cfg.autoinstall_iso is None:
        return
    spec = cfg.autoinstall_iso
    iso_path = dl.fetch(spec.url, f"{spec.id}.iso", spec.sha256)
    shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{spec.id}.iso")
    reporter.step(f"Zero-touch ISO staged ({spec.id})")


def boot_artifacts(
    ctx: Ctx,
    cfg: MediaConfig,
    dl: Downloader,
    cache: Cache,
    *,
    vtoy_mount: Path | None = None,
    reporter: Reporter,
) -> None:
    """Install Ventoy on *cfg.device*, mount the VTOY partition, stage all payload and ISOs.

    *vtoy_mount* is a test/override path: when provided the mount lifecycle is skipped and
    files are written directly there.  In production this is always ``None`` so the partition
    is discovered via lsblk and mounted to a temp dir, then unmounted+synced in a finally.
    """
    if not cfg.assume_yes:
        raise DeviceError(f"refusing to wipe {cfg.device}: not confirmed")
    validate(ctx, cfg.device)

    ventoy2disk = ensure_ventoy(ctx, dl, cache)
    if (
        ctx.ex.run(
            ["sh", str(ventoy2disk), "-i", cfg.device],
            sudo=True,
            stdin="y\ny\n",
        ).code
        != 0
    ):
        raise VentoyError(f"Ventoy install failed on {cfg.device}")
    reporter.step(f"Ventoy installed on {cfg.device}")

    with _mounted_vtoy(ctx, cfg.device, override=vtoy_mount) as mnt:
        _stage_payload(cfg, vtoy_mount=mnt, reporter=reporter)
        iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
        shutil.copyfile(iso_path, mnt / "ISO" / f"{cfg.iso.id}.iso")
        reporter.step(f"Fedora ISO staged ({cfg.iso.id})")
        _stage_autoinstall_iso(cfg, dl, vtoy_mount=mnt, reporter=reporter)
        extra_isos(cfg, vtoy_mount=mnt)
        if cfg.extra_isos:
            reporter.step(f"Staged {len(cfg.extra_isos)} extra ISO(s)")
        installers(cfg, vtoy_mount=mnt)
        if cfg.installers:
            reporter.step(f"Staged {len(cfg.installers)} installer(s)")


def update_stage(
    ctx: Ctx,
    cfg: MediaConfig,
    dl: Downloader,
    cache: Cache,
    *,
    vtoy_mount: Path | None = None,
    reporter: Reporter,
) -> None:
    """Non-destructive refresh: Ventoy2Disk.sh -u + re-stage payload; ISO only when refresh_iso."""
    validate(ctx, cfg.device)

    ventoy2disk = ensure_ventoy(ctx, dl, cache)
    if (
        ctx.ex.run(
            ["sh", str(ventoy2disk), "-u", cfg.device],
            sudo=True,
            stdin="y\ny\n",
        ).code
        != 0
    ):
        raise VentoyError(f"Ventoy update failed on {cfg.device}")
    reporter.step(f"Ventoy updated on {cfg.device}")

    with _mounted_vtoy(ctx, cfg.device, override=vtoy_mount) as mnt:
        _stage_payload(cfg, vtoy_mount=mnt, reporter=reporter)
        if cfg.refresh_iso:
            iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
            shutil.copyfile(iso_path, mnt / "ISO" / f"{cfg.iso.id}.iso")
            reporter.step(f"Fedora ISO refreshed ({cfg.iso.id})")
            _stage_autoinstall_iso(cfg, dl, vtoy_mount=mnt, reporter=reporter)
        extra_isos(cfg, vtoy_mount=mnt)
        if cfg.extra_isos:
            reporter.step(f"Staged {len(cfg.extra_isos)} extra ISO(s)")
        installers(cfg, vtoy_mount=mnt)
        if cfg.installers:
            reporter.step(f"Staged {len(cfg.installers)} installer(s)")


def extra_isos(cfg: MediaConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.extra_isos:
        shutil.copyfile(src, vtoy_mount / "ISO" / src.name)


def installers(cfg: MediaConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.installers:
        shutil.copyfile(src, vtoy_mount / "Installers" / src.name)


def mirror(ctx: Ctx, cfg: MediaConfig, *, vtoy_mount: Path) -> None:
    from devboost.core.settings import settings
    from devboost.media.mirror import mirror_dnf, mirror_flatpak, package_set

    dnf, flat = package_set(cfg.profiles, settings.root)
    mirror_dnf(ctx, dnf, vtoy_mount / "Bootstrap" / "repo" / "dnf")
    mirror_flatpak(ctx, flat, vtoy_mount / "Bootstrap" / "repo" / "flatpak")
