from __future__ import annotations

import re
from pathlib import Path

import pytest

from devboost.core.errors import MediaError
from devboost.media.catalog import (
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
    with pytest.raises(MediaError, match="riscv64"):
        iso_for("fedora-44", "riscv64")


def test_iso_for_unknown_os_raises() -> None:
    with pytest.raises(MediaError, match="unknown OS"):
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
    with pytest.raises(MediaError, match="invalid catalog"):
        load_catalog(p)


def test_load_catalog_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="invalid catalog"):
        load_catalog(tmp_path / "nope.toml")


def test_autoinstall_for_returns_netinst_spec() -> None:
    from devboost.media.catalog import autoinstall_for

    spec = autoinstall_for("fedora-44", "x86_64")
    assert spec is not None
    assert spec.id == "fedora-44-netinst"
    assert "netinst" in spec.url and len(spec.sha256) == 64


def test_autoinstall_for_aarch64_present() -> None:
    from devboost.media.catalog import autoinstall_for

    assert autoinstall_for("fedora-44", "aarch64") is not None


def test_autoinstall_for_missing_returns_none() -> None:
    from devboost.media.catalog import autoinstall_for

    assert autoinstall_for("fedora-44", "riscv64") is None  # arch not pinned
    assert autoinstall_for("ubuntu-99", "x86_64") is None   # unknown os


def test_load_catalog_parses_optional_autoinstall(tmp_path: Path) -> None:
    toml = _VALID + (
        "\n[fedora-99.autoinstall.x86_64]\n"
        'url = "https://x/f99-netinst.iso"\n'
        f'sha256 = "{"b" * 64}"\n'
    )
    p = tmp_path / "catalog.toml"
    p.write_text(toml, encoding="utf-8")
    cat = load_catalog(p)
    ai = cat["fedora-99"].autoinstall["x86_64"]
    assert ai.id == "fedora-99-netinst" and ai.edition == "netinst"


def test_load_catalog_entry_without_autoinstall_has_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(_VALID, encoding="utf-8")  # _VALID has no autoinstall table
    assert load_catalog(p)["fedora-99"].autoinstall == {}


def test_load_catalog_rejects_entry_without_isos(tmp_path: Path) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(
        '[broken]\nname = "B"\ndistro = "x"\nversion = "1"\nedition = "e"\n'
        "[broken.isos]\n",  # empty isos table → min_length=1 fails
        encoding="utf-8",
    )
    with pytest.raises(MediaError, match="invalid catalog"):
        load_catalog(p)


# ---------------------------------------------------------------------------
# Ventoy pin
# ---------------------------------------------------------------------------

def test_load_catalog_ignores_ventoy_section_in_os_validation(tmp_path: Path) -> None:
    """The [ventoy] block must NOT cause an 'invalid catalog' error during OS validation."""
    toml = _VALID + (
        "\n[ventoy]\n"
        'version = "1.1.16"\n'
        'url = "https://github.com/ventoy/Ventoy/releases/download/v1.1.16/ventoy-1.1.16-linux.tar.gz"\n'
        f'sha256 = "{"a" * 64}"\n'
    )
    p = tmp_path / "catalog.toml"
    p.write_text(toml, encoding="utf-8")
    # load_catalog should succeed and NOT include 'ventoy' as an OS entry
    cat = load_catalog(p)
    assert "ventoy" not in cat
    assert "fedora-99" in cat


def test_ventoy_pin_is_present_in_live_catalog() -> None:
    """The live catalog.toml (used by tests via settings) must have a valid [ventoy] block."""
    from devboost.media.catalog import VentoySpec, ventoy_pin

    pin = ventoy_pin()
    assert isinstance(pin, VentoySpec)
    assert pin.version == "1.1.16"
    assert pin.url.endswith(".tar.gz")
    import re
    assert re.fullmatch(r"[0-9a-f]{64}", pin.sha256)


def test_ventoy_pin_raises_for_missing_section(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """ventoy_pin() must raise MediaError when [ventoy] is absent."""
    from devboost.media.catalog import MediaError

    p = tmp_path / "catalog.toml"
    p.write_text(_VALID, encoding="utf-8")  # no [ventoy] block

    # Point the catalog module's settings reference at our stripped catalog path.
    class _FakeSettings:
        catalog_path = p

    monkeypatch.setattr("devboost.media.catalog.settings", _FakeSettings())

    # ventoy_pin uses @cache — clear between tests
    from devboost.media.catalog import ventoy_pin
    ventoy_pin.cache_clear()
    try:
        with pytest.raises(MediaError, match="ventoy"):
            ventoy_pin()
    finally:
        ventoy_pin.cache_clear()
