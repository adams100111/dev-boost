"""zsh on macOS: env + aliases load, fzf before atuin, plugins last (highlighting, then
autosuggestions), ~/.zshrc.local after everything; login files for zsh and `bash -lc`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import DOT, FRAGMENTS, MakeBin

ZSH = shutil.which("zsh")
BASH = shutil.which("bash") or "bash"
pytestmark = pytest.mark.skipif(ZSH is None, reason="zsh not installed")


def _zsh(home: Path, bin_dir: Path, script: str, *, brew: Path | None = None,
         login: bool = False) -> subprocess.CompletedProcess[str]:
    assert ZSH is not None
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "ZDOTDIR": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TERM": "dumb",
        "HOMEBREW_PREFIX": str(brew or home / "no-brew"),
    }
    flag = "-l" if login else "-i"
    return subprocess.run([ZSH, flag, "-c", script], env=env, capture_output=True, text=True,
                          timeout=30)


@pytest.fixture
def zsh_home(frag_home: Path, make_bin: MakeBin) -> Path:
    shutil.copy(DOT / "dot_zshrc", frag_home / ".zshrc")
    make_bin("ssh", "exit 0")  # `dev` is defined only where ssh exists
    return frag_home


def test_rc_files_parse() -> None:
    assert ZSH is not None
    for f in (FRAGMENTS / "shell.zsh", DOT / "dot_zshrc", DOT / "dot_zprofile"):
        res = subprocess.run([ZSH, "-n", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
    res = subprocess.run([BASH, "-n", str(DOT / "dot_bash_profile")], capture_output=True,
                         text=True)
    assert res.returncode == 0, res.stderr


def test_every_managed_rc_file_carries_the_marker() -> None:
    for f in (FRAGMENTS / "shell.zsh", DOT / "dot_zshrc", DOT / "dot_zprofile",
              DOT / "dot_bash_profile"):
        assert "devboost — managed by chezmoi" in f.read_text(encoding="utf-8"), f


def test_zshrc_loads_env_and_aliases_then_the_local_file(zsh_home: Path, bin_dir: Path) -> None:
    (zsh_home / ".zshrc.local").write_text("typeset -g LOCAL_SAW_DEV=$+functions[dev]\n",
                                           encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$LOCAL_SAW_DEV|$RIPGREP_CONFIG_PATH"')
    assert res.stdout.strip() == f"1|{zsh_home}/.config/ripgrep/ripgreprc", res.stderr


def test_fzf_loads_before_atuin_so_atuin_owns_ctrl_r(zsh_home: Path, bin_dir: Path,
                                                    make_bin: MakeBin) -> None:
    make_bin("fzf", "[ \"$1\" = --zsh ] && echo 'typeset -g FZF_ZSH_INIT=1'")
    make_bin("atuin", "echo 'typeset -g ATUIN_SAW_FZF=$+FZF_ZSH_INIT'")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$ATUIN_SAW_FZF"')
    assert res.stdout.strip() == "1", res.stderr


def test_plugins_load_last_highlighting_before_autosuggestions(
    zsh_home: Path, bin_dir: Path, tmp_path: Path
) -> None:
    brew = tmp_path / "brew"
    hl = brew / "share" / "zsh-syntax-highlighting" / "zsh-syntax-highlighting.zsh"
    au = brew / "share" / "zsh-autosuggestions" / "zsh-autosuggestions.zsh"
    hl.parent.mkdir(parents=True)
    au.parent.mkdir(parents=True)
    hl.write_text("typeset -g HL_AFTER_ALIASES=$+functions[dev]\n", encoding="utf-8")
    au.write_text("typeset -g AS_AFTER_HL=$+HL_AFTER_ALIASES\n", encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$HL_AFTER_ALIASES|$AS_AFTER_HL"', brew=brew)
    assert res.stdout.strip() == "1|1", res.stderr


def test_history_completion_cache_and_open_files(zsh_home: Path, bin_dir: Path) -> None:
    res = _zsh(zsh_home, bin_dir,
               'print -r -- "$HISTSIZE $SAVEHIST"; [[ -o sharehistory ]] && print share; ulimit -n')
    lines = res.stdout.split()
    assert lines[:3] == ["100000", "100000", "share"], res.stderr
    assert list((zsh_home / ".cache" / "zsh").glob("zcompdump-*")), "compinit dump not cached"
    if sys.platform == "darwin":
        assert int(lines[3]) > 256  # raised from macOS's default soft limit


def test_zprofile_sources_its_local_file(zsh_home: Path, bin_dir: Path) -> None:
    shutil.copy(DOT / "dot_zprofile", zsh_home / ".zprofile")
    (zsh_home / ".zprofile.local").write_text("typeset -gx ZPROFILE_LOCAL=1\n",
                                              encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$ZPROFILE_LOCAL"', login=True)
    assert res.stdout.strip().splitlines()[-1] == "1", res.stderr


def test_bash_login_gets_the_shared_env(frag_home: Path, bin_dir: Path) -> None:
    shutil.copy(DOT / "dot_bash_profile", frag_home / ".bash_profile")
    res = subprocess.run(
        [BASH, "-l", "-c", 'printf "%s" "$RIPGREP_CONFIG_PATH"'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(frag_home), "TERM": "dumb"},
        capture_output=True, text=True, timeout=30,
    )
    assert res.stdout.endswith(f"{frag_home}/.config/ripgrep/ripgreprc"), res.stderr


@pytest.mark.skipif(not Path("/opt/homebrew/bin/brew").exists(), reason="Homebrew not installed")
def test_zprofile_puts_homebrew_on_path_for_login_shells(zsh_home: Path, bin_dir: Path) -> None:
    shutil.copy(DOT / "dot_zprofile", zsh_home / ".zprofile")
    # HOMEBREW_REPOSITORY is set only by `brew shellenv` (/etc/paths.d may already list
    # /opt/homebrew/bin, so PATH alone would not prove the zprofile ran it).
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$HOMEBREW_REPOSITORY|$PATH"', login=True)
    repo, path = res.stdout.strip().splitlines()[-1].split("|", 1)
    assert repo == "/opt/homebrew", res.stderr
    assert "/opt/homebrew/bin" in path.split(":")
