"""VISUAL is Zed only in a local GUI session; EDITOR is fresh everywhere; git follows them."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

DOT = Path(__file__).resolve().parents[3] / "dotfiles"
ENV_SH = DOT / "dot_config" / "devboost" / "env.sh"
SHELL_BASH = DOT / "dot_config" / "devboost" / "shell.bash"
SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]


def _exe(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run(shell: str, tmp_path: Path, env: dict[str, str], *, zed: bool = True,
         uname: str = "Linux") -> tuple[str, str]:
    fake = tmp_path / "bin"
    fake.mkdir(parents=True)
    if zed:
        _exe(fake / "zed", "exit 0")
    _exe(fake / "uname", f"echo {uname}")
    script = f'. "{ENV_SH}"; printf "%s|%s" "${{VISUAL-<unset>}}" "$EDITOR"'
    out = subprocess.run(
        [shell, "-c", script],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path), **env},
        capture_output=True, text=True, check=True,
    )
    visual, editor = out.stdout.split("|")
    return visual, editor


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("display", [{"WAYLAND_DISPLAY": "wayland-0"}, {"DISPLAY": ":0"}])
def test_local_linux_gui_gets_zed(shell: str, tmp_path: Path, display: dict[str, str]) -> None:
    assert _run(shell, tmp_path, display) == ("zed --wait", "fresh")


@pytest.mark.parametrize("shell", SHELLS)
def test_linux_tty_has_no_visual(shell: str, tmp_path: Path) -> None:
    assert _run(shell, tmp_path, {}) == ("<unset>", "fresh")


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    "ssh", [{"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}, {"SSH_TTY": "/dev/pts/1"}]
)
def test_ssh_never_gets_zed_even_with_forwarded_display(
    shell: str, tmp_path: Path, ssh: dict[str, str]
) -> None:
    assert _run(shell, tmp_path, {"DISPLAY": "localhost:10.0", **ssh}) == ("<unset>", "fresh")


@pytest.mark.parametrize("shell", SHELLS)
def test_no_zed_on_path_means_no_visual(shell: str, tmp_path: Path) -> None:
    assert _run(shell, tmp_path, {"DISPLAY": ":0"}, zed=False) == ("<unset>", "fresh")


@pytest.mark.parametrize("shell", SHELLS)
def test_macos_local_session_gets_zed_without_display(shell: str, tmp_path: Path) -> None:
    assert _run(shell, tmp_path, {}, uname="Darwin") == ("zed --wait", "fresh")
    assert _run(shell, tmp_path / "s", {"SSH_TTY": "/dev/ttys001"}, uname="Darwin")[0] == "<unset>"


@pytest.mark.parametrize("shell", SHELLS)
def test_user_visual_kept_but_inherited_zed_dropped_outside_gui(shell: str, tmp_path: Path) -> None:
    assert _run(shell, tmp_path, {"VISUAL": "nvim"})[0] == "nvim"
    assert _run(shell, tmp_path / "t", {"VISUAL": "zed --wait"})[0] == "<unset>"


def test_env_sh_is_posix_and_shell_bash_sources_it_after_path() -> None:
    assert subprocess.run(["sh", "-n", str(ENV_SH)], capture_output=True).returncode == 0
    assert subprocess.run(["bash", "-n", str(SHELL_BASH)], capture_output=True).returncode == 0
    text = SHELL_BASH.read_text(encoding="utf-8")
    line = '[[ -r "${HOME}/.config/devboost/env.sh" ]] && source "${HOME}/.config/devboost/env.sh"'
    assert line in text
    env = ENV_SH.read_text(encoding="utf-8")
    assert env.index(".local/bin") < env.index("command -v zed")  # zed lookup needs ~/.local/bin


def test_git_core_editor_stays_unset() -> None:
    cfg = (DOT / "dot_config" / "git" / "config").read_text(encoding="utf-8")
    assert not any(ln.strip().startswith("editor") for ln in cfg.splitlines())
