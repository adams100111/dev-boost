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


def test_voxtype_arabic_targeted_apply_renders_both_configs(tmp_path: Path) -> None:
    """The exact `chezmoi apply <targets>` VoxtypeArabic runs, against real chezmoi."""
    import os
    import subprocess

    from devboost.core.errors import NeedsUser
    from devboost.core.osinfo import OsInfo
    from devboost.exec.executor import FakeExecutor
    from devboost.model import Ctx
    from devboost.modules import voxtype as vox

    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "voxtype").touch()  # the pinned binary is installed
    ex = FakeExecutor(present={"voxtype"})
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv("HOME", str(home))
        mp.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
        mp.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
        mp.setenv("DEVBOOST_NONINTERACTIVE", "1")
        mp.setattr(vox, "download_model", lambda ctx, name: None)
        with pytest.raises(NeedsUser):  # unattended: no daemon relaunch
            vox.VoxtypeArabic().install(Ctx(os=OsInfo("macos", "macos", "aarch64"), ex=ex))
    finally:
        mp.undo()
    argv = next(c for c in ex.calls if c[:2] == ["chezmoi", "apply"])
    assert CHEZMOI is not None
    # Real chezmoi reads the HOST os; the engine ran as macOS, so override the template
    # data (same seam as the chezmoi_apply fixture) or the Darwin-only AeroSpace target is
    # ignored and the apply fails on Linux CI.
    from tests.dotfiles.conftest import _data

    subprocess.run([CHEZMOI, *argv[1:2], "--no-tty", *argv[2:],
                    "--config", str(tmp_path / "chezmoi.toml"),
                    "--persistent-state", str(tmp_path / "arabic.boltdb"),
                    "--cache", str(tmp_path / "cache-arabic"),
                    "--override-data", _data("darwin", "macos")],
                   check=True, capture_output=True,
                   env={**os.environ, "HOME": str(home)})
    cfg = tomllib.loads((home / ".config" / "voxtype" / "config.toml").read_text("utf-8"))
    assert cfg["whisper"]["secondary_model"] == "large-v3-turbo"
    aero = tomllib.loads((home / ".config" / "aerospace" / "aerospace.toml").read_text("utf-8"))
    assert "ctrl-alt-d" in aero["mode"]["main"]["binding"]
    assert not (home / ".zshrc").exists()  # only the named targets are applied


def test_omarchy_apply_leaves_its_own_voxtype_config_untouched(tmp_path: Path) -> None:
    """Omarchy's `omarchy-voxtype-install` owns ~/.config/voxtype (`.chezmoiignore`)."""
    import json
    import os
    import subprocess

    from tests.dotfiles.render import SRC

    home = tmp_path / "home"
    cfg = home / ".config" / "voxtype" / "config.toml"
    cfg.parent.mkdir(parents=True)
    own = '[hotkey]\nenabled = false\n[whisper]\nmodel = "base.en"\n'
    cfg.write_text(own, encoding="utf-8")
    data = json.dumps({"chezmoi": {"os": "linux", "osRelease": {"id": "omarchy"}}})
    assert CHEZMOI is not None
    subprocess.run(
        [CHEZMOI, "apply", "--force", "--no-tty", "--source", str(SRC),
         "--destination", str(home), "--config", str(tmp_path / "chezmoi.toml"),
         "--persistent-state", str(tmp_path / "state.boltdb"),
         "--cache", str(tmp_path / "cache"), "--override-data", data],
        env={**os.environ, "HOME": str(home)}, capture_output=True, text=True, check=True,
    )
    assert cfg.read_text(encoding="utf-8") == own
    assert (home / ".config" / "devboost" / "shell.bash").exists()  # the apply did run
