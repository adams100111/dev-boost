"""shell.bash loads env.sh + aliases.sh; fzf ≥ 0.48 integration with a fallback; the
shared aliases.sh is valid bash and zsh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import FRAGMENTS, MakeBin

SHELL_BASH = FRAGMENTS / "shell.bash"
ALIASES = FRAGMENTS / "aliases.sh"
ZSH = shutil.which("zsh")


BASH = shutil.which("bash") or "bash"  # resolved here: the child PATH is minimal


def _bash(home: Path, bin_dir: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, "-c", f'source "$HOME/.config/devboost/shell.bash"; {script}'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home)},
        capture_output=True, text=True,
    )


def test_fragments_parse() -> None:
    for f in (SHELL_BASH, ALIASES):
        res = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
    if ZSH:
        res = subprocess.run([ZSH, "-n", str(ALIASES)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_shell_bash_loads_env_and_aliases(frag_home: Path, bin_dir: Path,
                                          make_bin: MakeBin) -> None:
    make_bin("ssh", "exit 0")
    make_bin("eza", "exit 0")
    res = _bash(frag_home, bin_dir, 'type -t dev; alias ls; printf "%s\\n" "$RIPGREP_CONFIG_PATH"')
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[0] == "function"
    assert "eza --group-directories-first" in lines[1]
    assert lines[2] == f"{frag_home}/.config/ripgrep/ripgreprc"


def test_modern_fzf_prints_its_own_bash_integration(frag_home: Path, bin_dir: Path,
                                                    make_bin: MakeBin) -> None:
    make_bin("fzf", '[ "$1" = "--bash" ] && { echo "FZF_BASH_INIT=new"; exit 0; }; exit 2')
    res = _bash(frag_home, bin_dir, 'printf "%s" "${FZF_BASH_INIT-<unset>}"')
    assert res.stdout == "new"


def test_old_fzf_falls_back_quietly(frag_home: Path, bin_dir: Path, make_bin: MakeBin) -> None:
    make_bin("fzf", 'echo "unknown option: $1" >&2; exit 2')  # fzf < 0.48 (Ubuntu 24.04)
    res = _bash(frag_home, bin_dir, 'printf "%s" "${FZF_BASH_INIT-<unset>}"')
    assert res.stdout == "<unset>"
    assert "unknown option" not in res.stderr
    assert "/usr/share/fzf/shell/key-bindings.bash" in SHELL_BASH.read_text(encoding="utf-8")


def test_aliases_never_shadow_zsh_path() -> None:
    # In zsh `path` is tied to $PATH — `local path=…` inside a function breaks every lookup.
    assert "local path=" not in ALIASES.read_text(encoding="utf-8")


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
def test_aliases_define_the_helpers_in_zsh(frag_home: Path, bin_dir: Path,
                                           make_bin: MakeBin) -> None:
    assert ZSH is not None
    make_bin("ssh", "exit 0")
    make_bin("claude", "exit 0")
    script = f'source "{frag_home}/.config/devboost/aliases.sh"; whence -w dev pw-workstation'
    res = subprocess.run(
        [ZSH, "-c", script],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(frag_home)},
        capture_output=True, text=True,
    )
    assert res.stdout.splitlines() == ["dev: function", "pw-workstation: function"]
