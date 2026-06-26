from __future__ import annotations

import re
from pathlib import Path

import pytest

from devboost.core.errors import UsbError
from devboost.usb.catalog import (
    catalog,
    default_iso,
    default_os,
    iso_for,
    load_catalog,
    supported,
)


def test_catalog_default_has_required_fields() -> None:
    iso = default_iso()
    assert iso.id in catalog()
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
    assert len(supported()) == len(catalog())


def test_iso_for_x86_64_returns_spec() -> None:
    spec = iso_for("fedora-44", "x86_64")
    assert spec.id == "fedora-44" and "x86_64" in spec.url


def test_iso_for_aarch64_returns_spec() -> None:
    spec = iso_for("fedora-44", "aarch64")
    assert spec.id == "fedora-44" and "aarch64" in spec.url


def test_iso_for_unsupported_arch_raises() -> None:
    with pytest.raises(UsbError, match="riscv64"):
        iso_for("fedora-44", "riscv64")


def test_iso_for_unknown_os_raises() -> None:
    with pytest.raises(UsbError, match="unknown OS"):
        iso_for("ubuntu-99", "x86_64")


def test_catalog_default_sha256_is_64_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", default_iso().sha256)


# --- loader validation (the value of moving pins into catalog.toml) -------------------

_VALID = """
[fedora-99]
name = "Fedora 99"
distro = "fedora"
version = "99"
edition = "Workstation-Live"

[fedora-99.isos.x86_64]
url = "https://x/f99.iso"
sha256 = "{sha}"
""".format(sha="a" * 64)


def test_load_catalog_parses_and_typed_isos(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(_VALID, encoding="utf-8")
    cat = load_catalog(p)
    spec = cat["fedora-99"].isos["x86_64"]
    assert spec.id == "fedora-99"            # id is derived from the table key
    assert spec.edition == "Workstation-Live"  # edition inherited from the Os entry
    assert spec.sha256 == "a" * 64


def test_load_catalog_rejects_bad_sha256(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(_VALID.replace("a" * 64, "tooshort"), encoding="utf-8")
    with pytest.raises(UsbError, match="invalid catalog"):
        load_catalog(p)


def test_load_catalog_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(UsbError, match="invalid catalog"):
        load_catalog(tmp_path / "nope.toml")


def test_load_catalog_rejects_entry_without_isos(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(
        '[broken]\nname = "B"\ndistro = "x"\nversion = "1"\nedition = "e"\n'
        "[broken.isos]\n",  # empty isos table → min_length=1 fails
        encoding="utf-8",
    )
    with pytest.raises(UsbError, match="invalid catalog"):
        load_catalog(p)
