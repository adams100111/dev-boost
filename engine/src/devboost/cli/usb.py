"""The `devboost usb` command: flags or wizard -> build/update a bootable Ventoy USB.

NOTE (frozen binary): when running from a frozen devboost binary, the staged injection archive
(dist/devboost-<arch>.tar.gz) must be present alongside the binary. Build it first via
``scripts/build-bundle.sh``; the frozen ``usb`` command does not rebuild the tarball itself.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated

import questionary
import typer

from devboost.core import log, osinfo
from devboost.core.errors import UsbError
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.usb import wizard
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.catalog import autoinstall_for, default_iso, iso_for
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import UrllibDownloader
from devboost.usb.preview import render_plan
from devboost.usb.probe import DiskState, probe
from devboost.usb.report import RichReporter


def _iso_note(cfg: UsbBuildConfig) -> str:
    """Best-effort combined ISO download size for the dry-run preview (never raises)."""
    specs = [cfg.iso] + ([cfg.autoinstall_iso] if cfg.autoinstall_iso is not None else [])
    try:
        cache = Cache(cfg.cache_dir)
        total = 0
        all_cached = True
        for spec in specs:
            if cache.has(f"{spec.id}.iso", spec.sha256):
                continue
            all_cached = False
            req = urllib.request.Request(spec.url, method="HEAD")
            with urllib.request.urlopen(req) as resp:
                total += int(resp.headers.get("Content-Length", 0) or 0)
        if all_cached:
            return "cached"
        return f"≈{total / 1e9:.1f} GB" if total else "unknown"
    except OSError:
        return "unknown"


def _summary_text(cfg: UsbBuildConfig) -> str:
    verb = "Updated" if cfg.mode == "update" else "Built"
    extras: list[str] = []
    if cfg.offline_mirror:
        extras.append("offline-mirror: yes")
    if cfg.extra_isos:
        extras.append(f"+{len(cfg.extra_isos)} extra ISO")
    tail = (" · " + " · ".join(extras)) if extras else ""
    media = "Workstation Live" + (
        " + netinst (zero-touch)" if cfg.autoinstall_iso is not None else ""
    )
    head = (
        f"✅ {verb} {cfg.device} — {cfg.iso.id} ({cfg.arch}) · media: {media} · "
        f"profiles: {' '.join(cfg.profiles)}{tail}"
    )
    if cfg.mode == "update":
        body = (
            "ISOs/secrets preserved. Reboot the target; "
            "the firstboot service re-runs your profiles."
        )
    else:
        body = (
            "Boot it: insert the USB → firmware boot menu → pick the USB → Fedora installs "
            "(auto/zero-touch or manual) → on first boot dev-boost installs your profiles. "
            'Bad update later? Reboot → GRUB "Fedora snapshots".'
        )
    return head + "\n" + body


def usb(
    device: Annotated[
        str | None, typer.Option(help="Target removable disk, e.g. /dev/sdb")
    ] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help="Catalog ISO id (default: fedora-44)")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Path | None, typer.Option(help="Path to secrets.age")] = None,
    cache_dir: Annotated[Path | None, typer.Option(help="Download cache dir")] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the wipe-confirmation prompt")
    ] = False,
    no_wizard: Annotated[
        bool, typer.Option("--no-wizard", help="Fail instead of prompting")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Resolve + print the plan; touch nothing")
    ] = False,
    refresh_iso: Annotated[
        bool, typer.Option("--refresh-iso", help="On update, also re-download the pinned ISO")
    ] = False,
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Wipe & rebuild even an existing dev-boost USB")
    ] = False,
) -> None:
    """Build (or non-destructively update) a dev-boost Ventoy USB."""
    if device is None and no_wizard:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)

    vtoy = Path(
        os.environ.get("VTOY_MOUNT", f"/run/media/{os.environ.get('USER', 'root')}/VTOY")
    )

    state: DiskState | None = None
    if device is None:
        ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
        cfg = wizard.run(ctx)
    else:
        os_info = osinfo.detect()
        ctx = Ctx(os=os_info, ex=RealExecutor())
        resolved_arch = arch or os_info.arch
        state = probe(ctx, device)

        if state.kind == "devboost" and not rebuild:
            mode, assume_yes = "update", True  # detected dev-boost stick → non-destructive update
        else:
            mode, assume_yes = "build", yes
            if not assume_yes and not dry_run:
                ok = questionary.confirm(
                    f"WIPE {device}? All data on it is destroyed.", default=False
                ).ask()
                if not (ok or False):
                    log.error("aborted")
                    raise typer.Exit(code=1)
                assume_yes = True

        try:
            os_id = iso or default_iso().id
            cfg = UsbBuildConfig(
                device=device,
                arch=resolved_arch,
                iso=iso_for(os_id, resolved_arch),
                autoinstall_iso=autoinstall_for(os_id, resolved_arch),
                profiles=tuple(profile) or ("full",),
                secrets_path=secrets,
                cache_dir=cache_dir or Path(gettempdir()) / "devboost-usb",
                mode=mode,  # type: ignore[arg-type]
                refresh_iso=refresh_iso,
                assume_yes=assume_yes,
            )
        except UsbError as exc:
            log.error(str(exc))
            raise typer.Exit(code=1) from exc

    if dry_run:
        if state is None:
            state = probe(ctx, cfg.device)
        typer.echo(render_plan(cfg, state, download_note=_iso_note(cfg)))
        raise typer.Exit()

    reporter = RichReporter()
    build(ctx, cfg, UrllibDownloader(Cache(cfg.cache_dir), reporter), vtoy_mount=vtoy,
          reporter=reporter)
    reporter.summary(_summary_text(cfg))
