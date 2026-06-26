"""The `devboost usb` command: flags or wizard -> build a bootable Ventoy USB.

NOTE (frozen binary): when running from a frozen devboost binary, the staged injection archive
(dist/devboost-<arch>.tar.gz) must be present alongside the binary. Build it first via
``scripts/build-bundle.sh``; the frozen ``usb`` command does not rebuild the tarball itself.
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.usb import wizard
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import UrllibDownloader
from devboost.usb.isos import FEDORA, default_iso


def usb(
    device: Annotated[
        str | None, typer.Option(help="Target removable disk, e.g. /dev/sdb")
    ] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help=f"ISO id: {', '.join(FEDORA)}")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Path | None, typer.Option(help="Path to secrets.age")] = None,
    cache_dir: Annotated[Path | None, typer.Option(help="Download cache dir")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    no_wizard: Annotated[
        bool, typer.Option("--no-wizard", help="Fail instead of prompting")
    ] = False,
) -> None:
    """Build a bootable dev-boost Ventoy USB (interactive, or fully via flags)."""
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    if device is None and not no_wizard:
        cfg = wizard.run(ctx)
    elif device is None:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)
    else:
        cfg = UsbBuildConfig(
            device=device,
            arch=arch or osinfo.detect().arch,
            iso=FEDORA[iso] if iso else default_iso(),
            profiles=tuple(profile) or ("full",),
            secrets_path=secrets,
            cache_dir=cache_dir or Path(gettempdir()) / "devboost-usb",
            assume_yes=yes,
        )
    vtoy = Path(
        os.environ.get("VTOY_MOUNT", f"/run/media/{os.environ.get('USER', 'root')}/VTOY")
    )
    build(ctx, cfg, UrllibDownloader(Cache(cfg.cache_dir)), vtoy_mount=vtoy)
    log.ok(f"usb: built {cfg.device} (Fedora {cfg.iso.id}, profiles {' '.join(cfg.profiles)})")
