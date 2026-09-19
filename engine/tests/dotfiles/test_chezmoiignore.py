"""The chezmoi source applies cleanly on each OS, with the right per-OS file set."""

from __future__ import annotations

import pytest

from .conftest import DOT, Apply

MAC_ONLY = (".zshrc", ".zprofile", ".bash_profile")
LINUX_ONLY = (".bashrc", ".bash-preexec.sh", ".config/systemd")


def test_macos_apply_succeeds_with_the_zsh_files(chezmoi_apply: Apply) -> None:
    # Before the fix this failed: `.chezmoi.osRelease` does not exist on Darwin.
    home = chezmoi_apply("darwin", "macos")
    for f in (*MAC_ONLY, ".config/devboost/shell.zsh", ".config/devboost/env.sh"):
        assert (home / f).exists(), f
    for f in (*LINUX_ONLY, ".config/caddy"):
        assert not (home / f).exists(), f


# The hermetic stand-in for the Fedora/Ubuntu VM rehearsal (ruling M-R8).
@pytest.mark.parametrize("distro", ["fedora", "ubuntu"])
def test_linux_apply_has_bash_and_no_macos_files(chezmoi_apply: Apply, distro: str) -> None:
    home = chezmoi_apply("linux", distro)
    for f in (*LINUX_ONLY, ".tmux.conf", ".config/caddy", ".config/devboost/shell.bash"):
        assert (home / f).exists(), f
    for f in MAC_ONLY:
        assert not (home / f).exists(), f


def test_omarchy_keeps_its_own_files(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("linux", "omarchy")
    for f in (".bashrc", ".tmux.conf", ".config/starship.toml", ".config/ghostty", *MAC_ONLY):
        assert not (home / f).exists(), f
    assert (home / ".config" / "devboost" / "shell.bash").exists()


def test_omarchy_guard_is_evaluated_only_on_linux() -> None:
    text = (DOT / ".chezmoiignore").read_text(encoding="utf-8")
    assert '{{ if and (eq .chezmoi.os "linux") (eq .chezmoi.osRelease.id "omarchy") -}}' in text
