from __future__ import annotations

import re

import pytest

from devboost.core.errors import UsbError
from devboost.usb.catalog import CATALOG, default_iso, default_os, iso_for, supported


def test_catalog_default_has_required_fields() -> None:
    iso = default_iso()
    assert iso.id in CATALOG
    assert iso.url.startswith("https://") and iso.url.endswith(".iso")
    assert iso.edition


def test_default_os_is_fedora_44() -> None:
    os_entry = default_os()
    assert os_entry.id == "fedora-44"
    assert os_entry.distro == "fedora" and os_entry.version == "44"
    assert "x86_64" in os_entry.isos


def test_supported_returns_friendly_named_entries() -> None:
    names = [o.name for o in supported()]
    assert any("Fedora 44" in n for n in names)
    assert len(supported()) == len(CATALOG)


def test_iso_for_x86_64_returns_spec() -> None:
    spec = iso_for("fedora-44", "x86_64")
    assert spec.id == "fedora-44" and "x86_64" in spec.url


def test_iso_for_unsupported_arch_raises() -> None:
    with pytest.raises(UsbError, match="aarch64"):
        iso_for("fedora-44", "aarch64")


def test_iso_for_unknown_os_raises() -> None:
    with pytest.raises(UsbError, match="unknown OS"):
        iso_for("ubuntu-99", "x86_64")


def test_catalog_default_sha256_is_64_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", default_iso().sha256)
