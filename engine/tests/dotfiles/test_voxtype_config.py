"""The one Voxtype config for every OS, with the opt-in Arabic secondary model."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.dotfiles.conftest import Apply
from tests.dotfiles.render import CHEZMOI, render_template

# Real chezmoi subprocess against the source tree: excluded from the fast lane
# (`pytest -m "not slow"`, ruling M5-D12).
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(CHEZMOI is None, reason="chezmoi not installed"),
]
REL = "dot_config/voxtype/config.toml.tmpl"


def _cfg(os_name: str, home: Path) -> tuple[str, dict[str, Any]]:
    raw = render_template(REL, os_name, home)
    return raw, tomllib.loads(raw)


@pytest.mark.parametrize(("os_name", "key"), [("darwin", "RIGHTALT"), ("linux", "SCROLLLOCK")])
def test_english_default_everywhere(os_name: str, key: str, tmp_path: Path) -> None:
    raw, cfg = _cfg(os_name, tmp_path)
    assert "devboost — managed by chezmoi" in raw
    assert "PLACEHOLDER" in raw  # the author's Omarchy hotkey goes here (D16)
    assert cfg["engine"] == "whisper"
    assert cfg["hotkey"] == {"key": key, "mode": "push_to_talk"}
    assert cfg["whisper"] == {"model": "small.en", "language": "en"}


def _arabic(home: Path) -> None:
    marker = home / ".config" / "devboost" / "voxtype-arabic"
    marker.parent.mkdir(parents=True)
    marker.touch()


def test_arabic_adds_an_on_demand_secondary_model(tmp_path: Path) -> None:
    _arabic(tmp_path)
    _, cfg = _cfg("linux", tmp_path)
    assert cfg["whisper"] == {
        "model": "small.en",
        "language": ["en", "ar"],
        "secondary_model": "large-v3-turbo",
        "cold_model_timeout_secs": 60,
    }
    assert "on_demand_loading" not in cfg["whisper"]  # would unload the primary too (D17)
    assert cfg["hotkey"]["model_modifier"] == "LEFTSHIFT"


def test_macos_arabic_has_no_model_modifier(tmp_path: Path) -> None:
    _arabic(tmp_path)
    _, cfg = _cfg("darwin", tmp_path)
    assert cfg["whisper"]["secondary_model"] == "large-v3-turbo"
    assert "model_modifier" not in cfg["hotkey"]  # ignored on macOS; AeroSpace binds it


@pytest.mark.parametrize(("os_name", "distro"), [("darwin", "macos"), ("linux", "fedora")])
def test_apply_writes_the_config(chezmoi_apply: Apply, os_name: str, distro: str) -> None:
    home = chezmoi_apply(os_name, distro)
    cfg = tomllib.loads((home / ".config" / "voxtype" / "config.toml").read_text("utf-8"))
    assert cfg["whisper"]["model"] == "small.en"
