from __future__ import annotations

from devboost.usb.isos import FEDORA, default_iso


def test_catalog_has_a_default_with_required_fields() -> None:
    iso = default_iso()
    assert iso.id in FEDORA
    assert iso.url.startswith("https://") and iso.url.endswith(".iso")
    assert len(iso.sha256) == 64 and iso.edition
