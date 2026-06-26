from __future__ import annotations

import pytest

from devboost.core.errors import UsbError
from devboost.usb.isos import FEDORA, default_iso, iso_for


def test_catalog_has_a_default_with_required_fields() -> None:
    iso = default_iso()
    assert iso.id in FEDORA
    assert iso.url.startswith("https://") and iso.url.endswith(".iso")
    assert len(iso.sha256) == 64 and iso.edition


def test_iso_for_x86_64_returns_spec() -> None:
    spec = iso_for("fedora-44", "x86_64")
    assert spec.id == "fedora-44"
    assert "x86_64" in spec.url


def test_iso_for_aarch64_raises_usberror() -> None:
    with pytest.raises(UsbError, match="aarch64"):
        iso_for("fedora-44", "aarch64")
