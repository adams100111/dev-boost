from __future__ import annotations

from devboost.core.settings import settings
from devboost.usb.mirror import package_set


def test_package_set_collects_dnf_and_flatpak_for_cli_and_apps() -> None:
    dnf, flat = package_set(("cli", "apps"), settings.root)
    assert "bat" in dnf                         # a cli package (from a PackageModule)
    assert "md.obsidian.Obsidian" in flat      # an apps flatpak id
