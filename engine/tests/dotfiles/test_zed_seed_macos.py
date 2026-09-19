"""The Zed seed (create_ files) is applied on macOS too — same ~/.config/zed path."""

from __future__ import annotations

import pytest

from .conftest import Apply

# Real chezmoi subprocess against the source tree: excluded from the fast lane
# (`pytest -m "not slow"`).
pytestmark = pytest.mark.slow


def test_chezmoi_seeds_zed_on_macos(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("darwin", "macos")
    assert (home / ".config" / "zed" / "settings.json").is_file()
    assert (home / ".config" / "zed" / "keymap.json").is_file()
