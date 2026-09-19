"""The Zed seed (create_ files) is applied on macOS too — same ~/.config/zed path."""

from __future__ import annotations

from .conftest import Apply


def test_chezmoi_seeds_zed_on_macos(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("darwin", "macos")
    assert (home / ".config" / "zed" / "settings.json").is_file()
    assert (home / ".config" / "zed" / "keymap.json").is_file()
