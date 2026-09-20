"""The AeroSpace config: a Ctrl+Alt layer on macOS, never applied on Linux."""

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
REL = "dot_config/aerospace/aerospace.toml.tmpl"


def _cfg(home: Path) -> dict[str, Any]:
    return tomllib.loads(render_template(REL, "darwin", home))


def _main(home: Path) -> dict[str, Any]:
    cfg = _cfg(home)
    assert cfg["start-at-login"] is True
    binding = cfg["mode"]["main"]["binding"]
    assert isinstance(binding, dict)
    return binding


def test_every_main_binding_is_on_ctrl_alt(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    assert keys, "no bindings rendered"
    assert all(k.startswith("ctrl-alt-") for k in keys), sorted(keys)


def test_workspaces_focus_and_move(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    for n in range(1, 10):
        assert keys[f"ctrl-alt-{n}"] == f"workspace {n}"
        assert keys[f"ctrl-alt-shift-{n}"] == f"move-node-to-workspace {n}"
    for key, direction in zip("hjkl", ("left", "down", "up", "right"), strict=True):
        assert keys[f"ctrl-alt-{key}"] == f"focus {direction}"
        assert keys[f"ctrl-alt-shift-{key}"] == f"move {direction}"


def test_config_version_2_keeps_the_bound_workspaces(tmp_path: Path) -> None:
    # Without config-version, `reload-config` warns; version 2 drops the inferred
    # persistent workspaces, so the nine bound ones are listed explicitly.
    cfg = _cfg(tmp_path)
    assert cfg["config-version"] == 2
    assert cfg["persistent-workspaces"] == [str(n) for n in range(1, 10)]


def test_nothing_binds_paste(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    assert not [k for k in keys if k.endswith("-v")]  # herdr owns Ctrl+V (spec §3)


def test_arabic_dictation_binding_only_with_the_marker(tmp_path: Path) -> None:
    assert "ctrl-alt-d" not in _main(tmp_path)
    marker = tmp_path / ".config" / "devboost" / "voxtype-arabic"
    marker.parent.mkdir(parents=True)
    marker.touch()
    assert _main(tmp_path)["ctrl-alt-d"] == (
        'exec-and-forget "$HOME/.local/bin/voxtype" record toggle --model large-v3-turbo'
    )  # the pinned binary (voxtype.bin_path), quoted for bash; never a Homebrew one


def test_macos_apply_writes_the_aerospace_config(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("darwin", "macos")
    assert (home / ".config" / "aerospace" / "aerospace.toml").is_file()


@pytest.mark.parametrize("distro", ["fedora", "ubuntu", "omarchy"])
def test_linux_apply_never_writes_the_aerospace_config(
    chezmoi_apply: Apply, distro: str
) -> None:
    home = chezmoi_apply("linux", distro)
    assert not (home / ".config" / "aerospace").exists()


def test_macos_apply_skips_the_xdg_config_next_to_a_legacy_one(chezmoi_apply: Apply) -> None:
    """I1: AeroSpace reports an ambiguity when ~/.aerospace.toml and the XDG config both
    exist, so a user's own ~/.aerospace.toml means dev-boost writes no XDG copy."""
    own = "# mine\n"
    home = chezmoi_apply("darwin", "macos", existing={".aerospace.toml": own})
    assert not (home / ".config" / "aerospace").exists()
    assert (home / ".aerospace.toml").read_text(encoding="utf-8") == own
    assert (home / ".zshrc").is_file()  # the rest still applies


def test_equal_sizes_has_a_key(tmp_path: Path) -> None:
    """Dragging a split, or closing one of three windows, leaves the rest uneven. Without
    a binding the only way back to an even split is the CLI or flattening the whole tree,
    which also undoes any nesting you meant to keep."""
    assert _main(tmp_path)["ctrl-alt-0"] == "balance-sizes"


def test_windows_land_only_where_devboost_installed_the_app(tmp_path: Path) -> None:
    """Placement rules must not assume apps dev-boost does not install: an earlier draft
    shipped Edge, Chrome, Slack, WhatsApp and Safari rules, copied from one machine."""
    rules = _cfg(tmp_path)["on-window-detected"]
    ids = {r["if"]["app-id"] for r in rules}
    assert ids == {
        "com.mitchellh.ghostty",   # ghostty module
        "dev.zed.Zed",             # zed module
        "md.obsidian",             # obsidian module
        "com.apple.systempreferences",  # ships with macOS; floated, not placed
    }
