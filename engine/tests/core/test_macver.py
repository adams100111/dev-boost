from __future__ import annotations

import pytest

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo


@pytest.mark.parametrize(
    ("version_id", "expected"),
    [("27.0", (27, 0)), ("26.4.1", (26, 4)), ("15", (15, 0)), ("", None), ("x.y", None)],
)
def test_macos_version_parses_major_minor(
    version_id: str, expected: tuple[int, int] | None
) -> None:
    assert macos_version(OsInfo("macos", "macos", "aarch64", version_id=version_id)) == expected


def test_macos_version_is_none_off_macos() -> None:
    assert macos_version(OsInfo("fedora", "fedora", "x86_64", version_id="44")) is None
