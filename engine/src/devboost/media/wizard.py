"""Interactive wizard: questionary prompts (each defaulted) -> MediaConfig.

After the device pick we probe (read-only) and branch: an existing dev-boost stick
offers a non-destructive update; a foreign Ventoy or blank stick confirms a wipe.
"""

from __future__ import annotations

import platform
from pathlib import Path
from tempfile import gettempdir

import questionary

from devboost.core.errors import DeviceError
from devboost.core.osinfo import family_of
from devboost.media.catalog import autoinstall_for, catalog, default_os, iso_for, supported
from devboost.media.config import MediaConfig
from devboost.media.devices import list_removable
from devboost.media.probe import probe
from devboost.model import Ctx

_PROFILES = ("full", "terminal", "devtools", "base", "cli", "shell", "gnome")


def _confirm_wipe(device: str, *, label: str) -> None:
    ok = questionary.confirm(f"{label} {device}? All data on it is destroyed.", default=False).ask()
    if not (ok or False):
        raise DeviceError("aborted: device wipe not confirmed")


def run(ctx: Ctx) -> MediaConfig:
    devices = list_removable(ctx)
    if not devices:
        raise DeviceError("no removable disk found — plug in a USB and retry")
    device = questionary.select(
        "Target USB device:",
        choices=[questionary.Choice(d.label(), value=d.path) for d in devices],
    ).ask()
    if device is None:
        raise DeviceError("aborted")

    state = probe(ctx, device)
    mode = "build"
    refresh_iso = False
    if state.kind == "devboost":
        built = state.marker.built_at if state.marker else "unknown"
        os_id = state.marker.os_id if state.marker else "?"
        action = questionary.select(
            f"This is a dev-boost USB ({os_id}, built {built}). What now?",
            choices=[
                questionary.Choice("Update (keep ISOs/secrets, no wipe)", value="update"),
                questionary.Choice("Rebuild (wipe everything)", value="build"),
            ],
            default="update",
        ).ask() or "update"
        mode = action
        if mode == "update":
            refresh_iso = questionary.confirm(
                "Also re-download the pinned Fedora ISO?", default=False
            ).ask() or False
        else:
            _confirm_wipe(device, label="REBUILD — WIPE")
    elif state.kind == "ventoy-other":
        _confirm_wipe(device, label="This is a non-dev-boost Ventoy stick. WIPE")
    else:
        _confirm_wipe(device, label="WIPE")

    arches = sorted({a for o in supported() for a in o.isos})
    host = platform.machine()
    arch = questionary.select(
        "Architecture:", choices=arches, default=host if host in arches else arches[0]
    ).ask()
    if arch is None:
        raise DeviceError("aborted")

    os_id = questionary.select(
        "Operating system:",
        choices=[questionary.Choice(o.name, value=o.id) for o in supported()],
        default=default_os().id,
    ).ask()
    if os_id is None:
        raise DeviceError("aborted")

    profiles = questionary.checkbox(
        "Profiles to install on first boot:",
        choices=[questionary.Choice(p, checked=(p == "full")) for p in _PROFILES],
    ).ask() or ["full"]
    secrets = questionary.path("Path to secrets.age (blank to skip):", default="").ask()
    cache = questionary.path(
        "Cache dir for downloads:", default=str(Path(gettempdir()) / "devboost-usb")
    ).ask()
    if cache is None:
        raise DeviceError("aborted")

    offline_mirror: bool = questionary.confirm(
        "Pre-mirror dnf+flatpak packages for OFFLINE install?"
        " (large — tens of GB; mise/npm/github tools still need network)",
        default=False,
    ).ask() or False

    return MediaConfig(
        device=device,
        arch=arch,
        iso=iso_for(os_id, arch),
        autoinstall_iso=autoinstall_for(os_id, arch),
        os_family=family_of(catalog()[os_id].distro),
        profiles=tuple(profiles),
        secrets_path=Path(secrets) if secrets else None,
        cache_dir=Path(cache),
        offline_mirror=offline_mirror,
        mode=mode,  # type: ignore[arg-type]
        refresh_iso=refresh_iso,
        assume_yes=True,
    )
