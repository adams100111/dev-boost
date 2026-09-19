from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from devboost.core.errors import MediaError
from devboost.core.settings import settings
from devboost.media import catalog


def test_xcode_pin_is_the_newest_ga() -> None:
    pin = catalog.xcode_pin()
    assert pin.version == "27.0"
    assert pin.ios_runtime == "27.0"
    assert pin.min_macos == (26, 6)


def test_voxtype_pin_assets_are_hashed_release_urls() -> None:
    pin = catalog.voxtype_pin()
    assert pin.version == "1.0.1"
    assert set(pin.assets) == {"rpm-x86_64", "deb-x86_64", "bin-aarch64"}
    for asset in pin.assets.values():
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
        assert asset.url.startswith(
            "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/"
        )


def test_os_catalog_still_loads_with_the_new_sections() -> None:
    assert catalog.load_catalog(settings.catalog_path)  # sections are stripped, not parsed


def test_bad_xcode_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        catalog._XcodeRow.model_validate(
            {"version": "latest", "ios_runtime": "27.0", "min_macos": "26.6"}
        )


@pytest.mark.parametrize(
    ("loader", "section"), [(catalog.xcode_pin, "xcode"), (catalog.voxtype_pin, "voxtype")]
)
def test_missing_section_raises_media_error(
    loader: Callable[[], object], section: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text('[ventoy]\nversion = "1"\n', encoding="utf-8")

    class _FakeSettings:
        catalog_path = p

    monkeypatch.setattr("devboost.media.catalog.settings", _FakeSettings())
    loader.cache_clear()  # type: ignore[attr-defined]
    try:
        with pytest.raises(MediaError, match=section):
            loader()
    finally:
        loader.cache_clear()  # type: ignore[attr-defined]
