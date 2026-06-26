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
from devboost.usb.isos import FEDORA, default_iso, iso_for

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
    if device is None:
        raise DeviceError("aborted")

    confirmed = questionary.confirm(
        f"WIPE {device}? All data on it is destroyed.", default=False
    ).ask()
    if not (confirmed or False):
        raise DeviceError("aborted: device wipe not confirmed")

    arch = questionary.select(
        "Architecture:",
        choices=["x86_64", "aarch64"],
        default=platform.machine(),
    ).ask()
    if arch is None:
        raise DeviceError("aborted")

    iso_id = questionary.select(
        "Fedora ISO:", choices=list(FEDORA), default=default_iso().id
    ).ask()
    if iso_id is None:
        raise DeviceError("aborted")

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
    if cache is None:
        raise DeviceError("aborted")

    offline_mirror: bool = questionary.confirm(
        "Pre-mirror dnf+flatpak packages for OFFLINE install?"
        " (large — tens of GB; mise/npm/github tools still need network)",
        default=False,
    ).ask() or False

    return UsbBuildConfig(
        device=device,
        arch=arch,
        iso=iso_for(iso_id, arch),
        profiles=tuple(profiles),
        secrets_path=Path(secrets) if secrets else None,
        cache_dir=Path(cache),
        offline_mirror=offline_mirror,
        assume_yes=True,
    )
