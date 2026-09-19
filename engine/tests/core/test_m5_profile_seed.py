"""M5-D9: the M5 profile keys exist before any M5 module declares them.

`validate_profiles` rejects a module whose `profiles` names a key missing from
profiles.toml (or from conftest's `profiles_file`), so Wave 0 seeds the keys empty and the
integration lane fills the member lists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.profiles import load_profiles
from devboost.core.settings import settings

M5_KEYS = ("macos-desktop", "ios", "macos-extras")


@pytest.mark.parametrize("key", M5_KEYS)
def test_real_profiles_declare_the_m5_keys(key: str) -> None:
    assert key in load_profiles(settings.profiles_path)


@pytest.mark.parametrize("key", M5_KEYS)
def test_fixture_profiles_declare_the_m5_keys(key: str, profiles_file: Path) -> None:
    assert key in load_profiles(profiles_file)
