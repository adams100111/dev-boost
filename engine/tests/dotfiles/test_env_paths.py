"""env.sh: PATH once and only for real dirs, ripgrep config, the macOS environment, and the
machine-local override hook."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import FRAGMENTS, MakeBin

ENV_SH = FRAGMENTS / "env.sh"
SHELLS = [s for s in ("sh", "dash", "bash", "zsh") if shutil.which(s)]
KEYS = ("PATH", "LANG", "LC_CTYPE", "XDG_CONFIG_HOME", "ANDROID_HOME", "RIPGREP_CONFIG_PATH")


def _env(shell: str, home: Path, bin_dir: Path, make_bin: MakeBin, *,
         uname: str = "Linux", extra: dict[str, str] | None = None) -> dict[str, str]:
    make_bin("uname", f"echo {uname}")
    fields = " ".join(f'"${{{k}-<unset>}}"' for k in KEYS)
    script = f'. "{ENV_SH}"; . "{ENV_SH}"; printf "%s\\n" {fields}'
    out = subprocess.run(
        [shell, "-c", script],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), **(extra or {})},
        capture_output=True, text=True, check=True,
    )
    return dict(zip(KEYS, out.stdout.splitlines(), strict=True))


@pytest.mark.parametrize("shell", SHELLS)
def test_user_bins_come_first_once_each(shell: str, tmp_path: Path, bin_dir: Path,
                                        make_bin: MakeBin) -> None:
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".dotnet" / "tools").mkdir(parents=True)
    path = _env(shell, tmp_path, bin_dir, make_bin)["PATH"].split(":")
    assert path[:2] == [f"{tmp_path}/.local/bin", f"{tmp_path}/.dotnet/tools"]
    assert path.count(f"{tmp_path}/.local/bin") == 1  # sourced twice, added once


@pytest.mark.parametrize("shell", SHELLS)
def test_missing_dirs_stay_off_path(shell: str, tmp_path: Path, bin_dir: Path,
                                    make_bin: MakeBin) -> None:
    path = _env(shell, tmp_path, bin_dir, make_bin)["PATH"]
    assert ".local/bin" not in path and ".dotnet/tools" not in path


@pytest.mark.parametrize("shell", SHELLS)
def test_ripgrep_reads_the_managed_config(shell: str, tmp_path: Path, bin_dir: Path,
                                          make_bin: MakeBin) -> None:
    got = _env(shell, tmp_path, bin_dir, make_bin)["RIPGREP_CONFIG_PATH"]
    assert got == f"{tmp_path}/.config/ripgrep/ripgreprc"


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_environment(shell: str, tmp_path: Path, bin_dir: Path,
                            make_bin: MakeBin) -> None:
    tools = tmp_path / "Library" / "Android" / "sdk" / "platform-tools"
    tools.mkdir(parents=True)
    env = _env(shell, tmp_path, bin_dir, make_bin, uname="Darwin", extra={"LC_CTYPE": "UTF-8"})
    assert env["LANG"] == "en_US.UTF-8"
    assert env["LC_CTYPE"] == "en_US.UTF-8"  # a bare UTF-8 breaks ssh/mosh to Linux
    assert env["XDG_CONFIG_HOME"] == f"{tmp_path}/.config"
    assert env["ANDROID_HOME"] == f"{tmp_path}/Library/Android/sdk"
    assert str(tools) in env["PATH"].split(":")


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_keeps_a_chosen_locale(shell: str, tmp_path: Path, bin_dir: Path,
                                      make_bin: MakeBin) -> None:
    env = _env(shell, tmp_path, bin_dir, make_bin, uname="Darwin",
               extra={"LANG": "de_DE.UTF-8", "LC_CTYPE": "de_DE.UTF-8"})
    assert (env["LANG"], env["LC_CTYPE"]) == ("de_DE.UTF-8", "de_DE.UTF-8")


@pytest.mark.parametrize("shell", SHELLS)
def test_linux_environment_is_left_alone(shell: str, tmp_path: Path, bin_dir: Path,
                                         make_bin: MakeBin) -> None:
    env = _env(shell, tmp_path, bin_dir, make_bin)
    assert env["LANG"] == env["XDG_CONFIG_HOME"] == env["ANDROID_HOME"] == "<unset>"


def test_env_sh_is_posix() -> None:
    assert subprocess.run(["sh", "-n", str(ENV_SH)], capture_output=True).returncode == 0
    # macOS `sh` is bash in POSIX mode and accepts bashisms; dash rejects them.
    if shutil.which("dash"):
        res = subprocess.run(["dash", "-n", str(ENV_SH)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
    if shutil.which("shellcheck"):
        res = subprocess.run(["shellcheck", "-s", "sh", str(ENV_SH)], capture_output=True,
                             text=True)
        assert res.returncode == 0, res.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_machine_local_overrides_win(shell: str, tmp_path: Path, bin_dir: Path,
                                     make_bin: MakeBin) -> None:
    # A local GUI session with Zed on PATH: without local.sh, VISUAL would be `zed --wait`.
    make_bin("zed", "exit 0")
    make_bin("uname", "echo Linux")
    local = tmp_path / ".config" / "devboost" / "local.sh"
    local.parent.mkdir(parents=True)
    local.write_text('export EDITOR=nvim\nexport VISUAL="code --wait"\n', encoding="utf-8")
    out = subprocess.run(
        [shell, "-c", f'. "{ENV_SH}"; printf "%s|%s" "$EDITOR" "${{VISUAL-<unset>}}"'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "DISPLAY": ":0"},
        capture_output=True, text=True, check=True,
    )
    assert out.stdout == "nvim|code --wait"


def test_local_overrides_file_is_never_managed() -> None:
    assert not (FRAGMENTS / "local.sh").exists()
    assert not any(FRAGMENTS.glob("*local.sh*"))  # nor a chezmoi-prefixed variant
