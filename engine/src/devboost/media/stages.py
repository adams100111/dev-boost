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
from devboost.media.autoinstall import (
    EMPTY_META_DATA,
    render_user_data,
)
from devboost.media.autoinstall import (
    render_kscfg as render_kscfg,
)
from devboost.media.cache import Cache
from devboost.media.config import MediaConfig
from devboost.media.devices import (
    owner_mount_opts,
    unmount_children,
    validate,
    vtoy_partition,
)
from devboost.media.download import Downloader
from devboost.media.marker import Marker, write_marker
from devboost.media.report import Reporter
from devboost.media.ventoy import ensure_ventoy
from devboost.model import Ctx

_PAIR = re.compile(r'(\w+)="([^"]*)"')


def render_ventoy_json(
    *,
    default_iso: str,
    autoinstall_iso: str | None,
    auto_install_template: str = "/Bootstrap/ks.cfg",
) -> str:
    """Generate ventoy.json: default boot + injection on the Live media; auto_install block.

    ``default_iso``/``autoinstall_iso`` are bare filenames (e.g. ``fedora-44.iso``).

    * **Fedora** (default): ``autoinstall_iso`` is the netinst filename; both ISOs appear in
      ``injection``; ``auto_install`` binds the netinst + ``/Bootstrap/ks.cfg``.
    * **Ubuntu**: ``autoinstall_iso`` equals ``default_iso`` (same live ISO); only one entry
      appears in ``injection``; ``auto_install`` binds that ISO + ``/Bootstrap/user-data``
      (pass ``auto_install_template="/Bootstrap/user-data"``).

    The ``auto_install`` block is omitted when ``autoinstall_iso`` is ``None``.
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
        # Only add to injection when it is a distinct ISO (Fedora netinst); for Ubuntu the
        # autoinstall ISO IS the live ISO so we must not add a duplicate injection entry.
        if autoinstall_iso != default_iso:
            injection.append(
                {"image": f"/ISO/{autoinstall_iso}", "archive": "/Bootstrap/devboost.tar.gz"}
            )
        data["auto_install"] = [
            {"image": f"/ISO/{autoinstall_iso}", "template": auto_install_template}
        ]
    return json.dumps(data, indent=2)


def _find_vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """Return the /dev path of *device*'s Ventoy data partition, or None."""
    return vtoy_partition(ctx, device)


def _run_ventoy(ctx: Ctx, script: Path, flag: str, device: str, *, what: str) -> None:
    """Run ``Ventoy2Disk.sh <flag> <device>`` and verify it actually did the work.

    Both of these are load-bearing, and neither is obvious:

    * **cwd must be the extracted tree.** Ventoy2Disk.sh builds its tool PATH from
      ``OLDDIR=$(pwd)``, captured *before* it cd's to its own directory.  Invoked from
      anywhere else its bundled mkexfatfs/vtoycli are unreachable, its tool check fails and
      it installs nothing.
    * **Its exit status is meaningless.** The script ends on a trailing ``cd "$OLDDIR"``
      block, so it reports 0 even when VentoyWorker.sh refused or failed outright.  Ventoy's
      own "successfully finished" line is the only trustworthy signal, and it is printed by
      every mode (install / non-destructive install / update).

    Verifying the effect on the disk instead is not enough: an install that refuses leaves
    the *previous* install's partitions in place, which look exactly like success.
    """
    res = ctx.ex.run(
        ["sh", "./Ventoy2Disk.sh", flag, device],
        sudo=True,
        stdin="y\ny\n",
        cwd=script.parent,
    )
    out = (res.stdout + res.stderr).strip()
    if "successfully finished" not in out:
        raise VentoyError(
            f"Ventoy {what} did not complete on {device} (Ventoy2Disk.sh exited "
            f"{res.code}; it exits 0 even on failure)"
            + (f" — Ventoy said:\n{out}" if out else "")
        )


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
        # uid=/gid= so _stage_payload's stdlib writes land as the invoking user: mounting
        # needs sudo, and exfat takes its ownership from the mounting process.
        if ctx.ex.run(
            ["mount", "-o", owner_mount_opts(), part, str(mnt)], sudo=True
        ).code != 0:
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
    """Lay out ventoy.json + autoinstall config + injection archive + secrets + marker.

    Dispatches by ``cfg.os_family``:
    * ``"fedora"`` (default) — stages ``ks.cfg``; ``auto_install`` binds the netinst ISO.
    * ``"debian"``           — stages ``user-data`` + ``meta-data``; ``auto_install`` binds
                               the live ISO (no separate netinst for Ubuntu).
    """
    boot = vtoy_mount / "Bootstrap"
    for d in ("ISO", "Bootstrap", "Installers", "ventoy"):
        (vtoy_mount / d).mkdir(parents=True, exist_ok=True)

    if cfg.os_family == "debian":
        # Ubuntu/Debian: autoinstall runs off the live ISO itself via Ventoy user-data injection.
        live_name = f"{cfg.iso.id}.iso"
        (vtoy_mount / "ventoy" / "ventoy.json").write_text(
            render_ventoy_json(
                default_iso=live_name,
                autoinstall_iso=live_name,
                auto_install_template="/Bootstrap/user-data",
            ),
            encoding="utf-8",
        )
        (boot / "user-data").write_text(
            render_user_data(cfg.profiles, arch=cfg.arch), encoding="utf-8"
        )
        (boot / "meta-data").write_text(EMPTY_META_DATA, encoding="utf-8")
    else:
        # Fedora (default): autoinstall uses a separate netinst ISO + Kickstart template.
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
    # Ubuntu/Debian: no separate autoinstall ISO — the live ISO carries the installer.
    if cfg.os_family == "debian":
        return
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
    unmount_children(ctx, cfg.device)  # the wipe is confirmed → clear udisks2 auto-mounts
    validate(ctx, cfg.device)

    ventoy2disk = ensure_ventoy(ctx, dl, cache)
    # -I (force), not -i: `-i` refuses outright when the disk already contains Ventoy
    # ("please use -I option" — VentoyWorker.sh), which is every rebuild and every stick that
    # has ever been a Ventoy drive. The wipe is confirmed by this point, so forcing is what
    # the user asked for.
    _run_ventoy(ctx, ventoy2disk, "-I", cfg.device, what="install")
    reporter.step(f"Ventoy installed on {cfg.device}")

    with _mounted_vtoy(ctx, cfg.device, override=vtoy_mount) as mnt:
        _stage_payload(cfg, vtoy_mount=mnt, reporter=reporter)
        iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
        shutil.copyfile(iso_path, mnt / "ISO" / f"{cfg.iso.id}.iso")
        _os_label = "Ubuntu" if cfg.os_family == "debian" else "Fedora"
        reporter.step(f"{_os_label} ISO staged ({cfg.iso.id})")
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
    # Reaching here means this device was chosen for an update (Ventoy2Disk.sh -u rewrites its
    # boot area), so its own auto-mounted VTOY partition may be cleared — GNOME mounts it the
    # moment a finished dev-boost stick is plugged in.
    unmount_children(ctx, cfg.device)
    validate(ctx, cfg.device)

    ventoy2disk = ensure_ventoy(ctx, dl, cache)
    _run_ventoy(ctx, ventoy2disk, "-u", cfg.device, what="update")
    reporter.step(f"Ventoy updated on {cfg.device}")

    with _mounted_vtoy(ctx, cfg.device, override=vtoy_mount) as mnt:
        _stage_payload(cfg, vtoy_mount=mnt, reporter=reporter)
        if cfg.refresh_iso:
            iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
            shutil.copyfile(iso_path, mnt / "ISO" / f"{cfg.iso.id}.iso")
            _os_label = "Ubuntu" if cfg.os_family == "debian" else "Fedora"
            reporter.step(f"{_os_label} ISO refreshed ({cfg.iso.id})")
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
