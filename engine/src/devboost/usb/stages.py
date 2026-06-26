"""Builder stages: install Ventoy + lay out the USB; optional extras."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from devboost import __version__
from devboost.core.errors import DeviceError, VentoyError
from devboost.exec.resources import resource_path
from devboost.model import Ctx
from devboost.usb.config import UsbBuildConfig
from devboost.usb.devices import validate
from devboost.usb.download import Downloader
from devboost.usb.marker import Marker, write_marker
from devboost.usb.report import Reporter


def render_kscfg(
    template: str, profiles: tuple[str, ...], *, offline: bool = False
) -> str:
    install_cmd = "devboost install " + " ".join(profiles)
    if offline:
        install_cmd += " --offline"
    return template.replace("devboost install full", install_cmd)


def _stage_payload(cfg: UsbBuildConfig, *, vtoy_mount: Path, reporter: Reporter) -> None:
    """Lay out ventoy.json + ks.cfg + injection archive + secrets + marker (no wipe, no ISO)."""
    boot = vtoy_mount / "Bootstrap"
    for d in ("ISO", "Bootstrap", "Installers", "ventoy"):
        (vtoy_mount / d).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resource_path("ventoy", "ventoy.json"), vtoy_mount / "ventoy" / "ventoy.json")
    kscfg = resource_path("ventoy", "ks.cfg").read_text(encoding="utf-8")
    (boot / "ks.cfg").write_text(
        render_kscfg(kscfg, cfg.profiles, offline=cfg.offline_mirror), encoding="utf-8"
    )
    tarball = resource_path("dist", f"devboost-{cfg.arch}.tar.gz")
    if not tarball.exists():
        raise VentoyError(f"injection archive missing: {tarball} (run scripts/build-bundle.sh)")
    shutil.copyfile(tarball, boot / "devboost.tar.gz")
    if cfg.secrets_path is not None:
        shutil.copyfile(cfg.secrets_path, boot / "secrets.age")
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


def boot_artifacts(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if not cfg.assume_yes:
        raise DeviceError(f"refusing to wipe {cfg.device}: not confirmed")
    validate(ctx, cfg.device)
    if ctx.ex.run(["ventoy", "-i", cfg.device], sudo=True).code != 0:
        raise VentoyError(f"ventoy install failed on {cfg.device}")
    reporter.step(f"Ventoy installed on {cfg.device}")
    _stage_payload(cfg, vtoy_mount=vtoy_mount, reporter=reporter)
    iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
    shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{cfg.iso.id}.iso")
    reporter.step(f"Fedora ISO staged ({cfg.iso.id})")


def update_stage(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    """Non-destructive refresh: ventoy -u + re-stage payload; ISO only when refresh_iso."""
    validate(ctx, cfg.device)
    if ctx.ex.run(["ventoy", "-u", cfg.device], sudo=True).code != 0:
        raise VentoyError(f"ventoy update failed on {cfg.device}")
    reporter.step(f"Ventoy updated on {cfg.device}")
    _stage_payload(cfg, vtoy_mount=vtoy_mount, reporter=reporter)
    if cfg.refresh_iso:
        iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
        shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{cfg.iso.id}.iso")
        reporter.step(f"Fedora ISO refreshed ({cfg.iso.id})")


def extra_isos(cfg: UsbBuildConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.extra_isos:
        shutil.copyfile(src, vtoy_mount / "ISO" / src.name)


def installers(cfg: UsbBuildConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.installers:
        shutil.copyfile(src, vtoy_mount / "Installers" / src.name)


def mirror(ctx: Ctx, cfg: UsbBuildConfig, *, vtoy_mount: Path) -> None:
    from devboost.core.settings import settings
    from devboost.usb.mirror import mirror_dnf, mirror_flatpak, package_set

    dnf, flat = package_set(cfg.profiles, settings.root)
    mirror_dnf(ctx, dnf, vtoy_mount / "Bootstrap" / "repo" / "dnf")
    mirror_flatpak(ctx, flat, vtoy_mount / "Bootstrap" / "repo" / "flatpak")
