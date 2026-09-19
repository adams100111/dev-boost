"""Terminal configs: Ghostty per OS (and valid, when Ghostty is installed); WezTerm on
Darwin; no terminal binds Ctrl+V (herdr --remote owns image paste)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import DOT, Render

GHOSTTY = DOT / "dot_config" / "ghostty" / "config.tmpl"
WEZ = DOT / "dot_config" / "wezterm"
_APP = Path("/Applications/Ghostty.app/Contents/MacOS/ghostty")
GHOSTTY_BIN = shutil.which("ghostty") or (str(_APP) if _APP.exists() else None)


def _settings(text: str) -> list[tuple[str, str]]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out.append((key.strip(), value.strip()))
    return out


def _binds(settings: list[tuple[str, str]]) -> list[str]:
    return [v for k, v in settings if k == "keybind"]


def test_ghostty_macos(chezmoi_render: Render) -> None:
    s = _settings(chezmoi_render(GHOSTTY, "darwin", "macos"))
    assert ("macos-option-as-alt", "left") in s  # right Option keeps typing accents
    assert ("macos-titlebar-style", "tabs") in s
    assert ("window-decoration", "none") not in s
    binds = _binds(s)
    for b in binds:
        if b.startswith("ctrl+shift+"):
            rest = b.removeprefix("ctrl+shift+")
            assert f"super+{rest}" in binds or f"super+shift+{rest}" in binds, b
    # Ctrl+- is undo in zsh/readline: font size is Cmd-only on macOS.
    triggers = [b.partition("=")[0] for b in binds]
    for key in ("equal", "minus", "zero"):
        assert f"ctrl+{key}" not in triggers, key
        assert f"super+{key}" in triggers, key


def test_ghostty_linux(chezmoi_render: Render) -> None:
    s = _settings(chezmoi_render(GHOSTTY, "linux", "fedora"))
    assert not any(k.startswith("macos-") for k, _ in s)
    assert not any(b.startswith("super+") for b in _binds(s))
    assert ("window-decoration", "none") in s
    triggers = [b.partition("=")[0] for b in _binds(s)]
    assert {"ctrl+equal", "ctrl+minus", "ctrl+zero"} <= set(triggers)


@pytest.mark.parametrize(("os_name", "distro"), [("darwin", "macos"), ("linux", "fedora")])
def test_ghostty_everywhere(chezmoi_render: Render, os_name: str, distro: str) -> None:
    s = _settings(chezmoi_render(GHOSTTY, os_name, distro))
    for pair in (("theme", "Catppuccin Mocha"), ("shell-integration", "detect"),
                 ("shell-integration-features", "ssh-env,ssh-terminfo"),
                 ("notify-on-command-finish", "unfocused")):
        assert pair in s, pair
    triggers = [b.partition("=")[0] for b in _binds(s)]
    assert "ctrl+v" not in triggers
    if os_name == "darwin":
        assert "super+v" in triggers
    assert all("toggle_zoom" not in b.replace("toggle_split_zoom", "") for b in _binds(s))


@pytest.mark.skipif(GHOSTTY_BIN is None, reason="ghostty not installed")
def test_ghostty_accepts_the_rendered_config(chezmoi_render: Render, tmp_path: Path) -> None:
    assert GHOSTTY_BIN is not None
    os_name, distro = ("darwin", "macos") if sys.platform == "darwin" else ("linux", "fedora")
    cfg = tmp_path / "config"
    cfg.write_text(chezmoi_render(GHOSTTY, os_name, distro), encoding="utf-8")
    res = subprocess.run([GHOSTTY_BIN, "+validate-config", f"--config-file={cfg}"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


def test_wezterm_never_binds_ctrl_v_and_paste_lua_is_gone() -> None:
    assert not (WEZ / "config" / "paste.lua").exists()
    assert "config.paste" not in (WEZ / "wezterm.lua").read_text(encoding="utf-8")
    for f in WEZ.rglob("*.lua"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r'key\s*=\s*"v",\s*mods\s*=\s*"CTRL"\s*,', text), f


def test_wezterm_darwin_keys() -> None:
    keys = (WEZ / "config" / "keys.lua").read_text(encoding="utf-8")
    assert 'wezterm.target_triple:find("darwin")' in keys
    assert '{ key = "a", mods = "CTRL", timeout_milliseconds = 1000 }' in keys  # macOS leader
    assert '{ key = "Space", mods = "CTRL", timeout_milliseconds = 1000 }' in keys
    assert "config.send_composed_key_when_left_alt_is_pressed = false" in keys
    assert 'mods = "SUPER|SHIFT", action = act.DetachDomain' in keys
    # With Ctrl+A as the leader, pressing it twice still sends Ctrl+A (line start).
    assert ('{ key = "a", mods = "LEADER|CTRL", action = act.SendKey({ key = "a", '
            'mods = "CTRL" }) }') in keys


@pytest.mark.skipif(shutil.which("luac") is None, reason="luac not installed")
def test_wezterm_lua_compiles() -> None:
    for f in WEZ.rglob("*.lua"):
        res = subprocess.run(["luac", "-p", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
