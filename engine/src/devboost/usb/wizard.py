"""Interactive wizard: questionary prompts (each defaulted) -> UsbBuildConfig."""

from __future__ import annotations

import platform
from pathlib import Path
from tempfile import gettempdir

import questionary

from devboost.core.errors import DeviceError
from devboost.model import Ctx
from devboost.usb.config import UsbBuildConfig
from devboost.usb.devices import list_removable
from devboost.usb.isos import FEDORA, default_iso

_PROFILES = ("full", "terminal", "devtools", "base", "cli", "shell", "gnome")


def run(ctx: Ctx) -> UsbBuildConfig:
    devices = list_removable(ctx)
    if not devices:
        raise DeviceError("no removable disk found — plug in a USB and retry")
    device = questionary.select(
        "Target USB device (WILL BE WIPED):",
        choices=[questionary.Choice(d.label(), value=d.path) for d in devices],
    ).ask()
    # Distinct, safe labels like:  /dev/sdb  —  SanDisk Ultra (usb)  —  32G  [sn:4C53]
    # (list_removable already filtered to removable + unmounted disks; the builder re-validate()s.)

    arch = questionary.select(
        "Architecture:",
        choices=["x86_64", "aarch64"],
        default=platform.machine(),
    ).ask()
    iso_id = questionary.select(
        "Fedora ISO:", choices=list(FEDORA), default=default_iso().id
    ).ask()
    profiles = questionary.checkbox(
        "Profiles to install on first boot:",
        choices=[questionary.Choice(p, checked=(p == "full")) for p in _PROFILES],
    ).ask() or ["full"]
    secrets = questionary.path(
        "Path to secrets.age (blank to skip):", default=""
    ).ask()
    cache = questionary.path(
        "Cache dir for downloads:",
        default=str(Path(gettempdir()) / "devboost-usb"),
    ).ask()

    return UsbBuildConfig(
        device=device,
        arch=arch,
        iso=FEDORA[iso_id],
        profiles=tuple(profiles),
        secrets_path=Path(secrets) if secrets else None,
        cache_dir=Path(cache),
    )
