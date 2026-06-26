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

import questionary
import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.usb import wizard
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.catalog import CATALOG, default_iso, iso_for
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import UrllibDownloader


def usb(
    device: Annotated[
        str | None, typer.Option(help="Target removable disk, e.g. /dev/sdb")
    ] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help=f"ISO id: {', '.join(CATALOG)}")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Path | None, typer.Option(help="Path to secrets.age")] = None,
    cache_dir: Annotated[Path | None, typer.Option(help="Download cache dir")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    no_wizard: Annotated[
        bool, typer.Option("--no-wizard", help="Fail instead of prompting")
    ] = False,
) -> None:
    """Build a bootable dev-boost Ventoy USB (interactive, or fully via flags)."""
    if device is None and no_wizard:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)

    vtoy = Path(
        os.environ.get("VTOY_MOUNT", f"/run/media/{os.environ.get('USER', 'root')}/VTOY")
    )

    if device is None:
        ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
        cfg = wizard.run(ctx)
    else:
        os_info = osinfo.detect()
        resolved_arch = arch or os_info.arch

        assume_yes = yes
        if not assume_yes:
            ok = questionary.confirm(
                f"WIPE {device}? All data on it is destroyed.", default=False
            ).ask()
            if not (ok or False):
                log.error("aborted")
                raise typer.Exit(code=1)
            assume_yes = True

        cfg = UsbBuildConfig(
            device=device,
            arch=resolved_arch,
            iso=iso_for(iso, resolved_arch) if iso else iso_for(default_iso().id, resolved_arch),
            profiles=tuple(profile) or ("full",),
            secrets_path=secrets,
            cache_dir=cache_dir or Path(gettempdir()) / "devboost-usb",
            assume_yes=assume_yes,
        )
        ctx = Ctx(os=os_info, ex=RealExecutor())

    build(ctx, cfg, UrllibDownloader(Cache(cfg.cache_dir)), vtoy_mount=vtoy)
    log.ok(f"usb: built {cfg.device} (Fedora {cfg.iso.id}, profiles {' '.join(cfg.profiles)})")
