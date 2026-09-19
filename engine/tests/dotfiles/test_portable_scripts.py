"""The resource probe on Linux and macOS, and every surface that reads it."""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from .conftest import DOT, MakeBin

PROBE = DOT / "dot_local" / "bin" / "executable_devboost-resources"
RESOURCES = DOT / "dot_config" / "tmux" / "executable_resources.sh"
PW_AUTO = DOT / "dot_config" / "tmux" / "executable_pw-autoregister.sh"
STATUSLINE = DOT / "private_dot_claude" / "executable_statusline.sh"
STARSHIP = DOT / "dot_config" / "starship.toml"
STATUS_LUA = DOT / "dot_config" / "wezterm" / "config" / "status.lua"
BASH = shutil.which("bash") or "bash"

DF = ("echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'; "
      "echo '/dev/disk3s5 971298980 68717056 875921296 8% /System/Volumes/Data'")


def _probe(bin_dir: Path, extra: dict[str, str]) -> str:
    return subprocess.run(
        ["sh", str(PROBE)], env={"PATH": f"{bin_dir}:/usr/bin:/bin", **extra},
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_probe_on_macos(bin_dir: Path, make_bin: MakeBin) -> None:
    make_bin("uname", "echo Darwin")
    make_bin("sysctl", "echo 25769803776")  # 24 GiB
    make_bin("vm_stat", "cat <<'EOF'\n"
             "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
             "Pages free:                                    37107.\n"
             "Pages active:                                 631665.\n"
             "Pages inactive:                               629739.\n"
             "Pages speculative:                               466.\n"
             "EOF")
    make_bin("df", DF)
    # used = total - (free + inactive + speculative) * page size → 57 %; 875921296 KiB → 835 G
    assert _probe(bin_dir, {}) == "57 8 835"


def test_probe_on_linux(bin_dir: Path, make_bin: MakeBin, tmp_path: Path) -> None:
    make_bin("uname", "echo Linux")
    make_bin("df", DF)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16000000 kB\nMemAvailable:    4000000 kB\n",
                       encoding="utf-8")
    assert _probe(bin_dir, {"DEVBOOST_MEMINFO": str(meminfo)}) == "75 8 835"


@pytest.fixture
def probe_home(tmp_path: Path) -> tuple[Path, Path]:
    """A HOME whose devboost-resources prints whatever ``<home>/probe.out`` holds."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fake = home / ".local" / "bin" / "devboost-resources"
    fake.write_text(f'#!/bin/sh\ncat "{home}/probe.out"\n', encoding="utf-8")
    fake.chmod(0o755)
    return home, home / "probe.out"


def _tmux_segment(home: Path) -> str:
    return subprocess.run(["sh", str(RESOURCES)], env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, check=True).stdout


def test_tmux_segment_colors_and_alert(probe_home: tuple[Path, Path]) -> None:
    home, out = probe_home
    out.write_text("40 50 100\n", encoding="utf-8")
    seg = _tmux_segment(home)
    assert "#a6e3a1]󰍛 40%" in seg and "#94e2d5]󰋊 100G" in seg
    out.write_text("65 85 100\n", encoding="utf-8")
    seg = _tmux_segment(home)
    assert "#f9e2af]󰍛 65%" in seg and "#f38ba8]󰋊 100G" in seg
    out.write_text("85 50 5\n", encoding="utf-8")
    assert "⚠" in _tmux_segment(home)
    out.write_text("", encoding="utf-8")  # probe failed → print nothing, never an error
    assert _tmux_segment(home) == ""


def _starship_module(name: str, home: Path, out: Path, value: str) -> tuple[bool, str]:
    mod = tomllib.loads(STARSHIP.read_text(encoding="utf-8"))["custom"][name]
    out.write_text(value + "\n", encoding="utf-8")
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    when = subprocess.run(["sh", "-c", mod["when"]], env=env).returncode == 0
    cmd = subprocess.run(["sh", "-c", mod["command"]], env=env, capture_output=True, text=True)
    return when, cmd.stdout


def test_starship_gauges_read_the_probe(probe_home: tuple[Path, Path]) -> None:
    home, out = probe_home
    assert _starship_module("ram_ok", home, out, "40 50 100") == (True, "40%")
    assert _starship_module("ram_warn", home, out, "40 50 100")[0] is False
    assert _starship_module("ram_warn", home, out, "65 50 100")[0] is True
    assert _starship_module("ram_crit", home, out, "85 50 100")[0] is True
    assert _starship_module("disk_ok", home, out, "40 50 100") == (True, "100G")
    assert _starship_module("disk_crit", home, out, "40 85 100")[0] is True
    assert _starship_module("res_alert", home, out, "40 50 100")[0] is False
    assert _starship_module("res_alert", home, out, "85 50 5") == (True, "RAM 85% · DISK 5G")


def test_no_surface_reads_proc_or_gnu_df_directly() -> None:
    for f in (RESOURCES, STARSHIP, STATUS_LUA, STATUSLINE):
        text = f.read_text(encoding="utf-8")
        assert "/proc/meminfo" not in text and "-BG" not in text, f
        assert "devboost-resources" in text, f


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")
def test_claude_statusline_uses_the_probe(probe_home: tuple[Path, Path], tmp_path: Path) -> None:
    home, out = probe_home
    payload = json.dumps({"model": {"display_name": "Opus"}, "cwd": str(tmp_path),
                          "context_window": {"used_percentage": 10},
                          "cost": {"total_cost_usd": 0.5}})
    env = {"HOME": str(home), "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "COLUMNS": "200"}
    out.write_text("40 50 100\n", encoding="utf-8")
    line = subprocess.run([BASH, str(STATUSLINE)], input=payload, env=env,
                          capture_output=True, text=True, check=True).stdout
    assert "40%" in line and "100G" in line
    out.write_text("85 50 100\n", encoding="utf-8")
    line = subprocess.run([BASH, str(STATUSLINE)], input=payload, env=env,
                          capture_output=True, text=True, check=True).stdout
    assert "48;2;243;139;168" in line  # the whole row flooded red when critical


def _pw_autoregister(bin_dir: Path, make_bin: MakeBin, tmp_path: Path, timeout_name: str | None,
                     ) -> str:
    log = tmp_path / "claude.log"
    make_bin("tmux", "echo 'SSH_CONNECTION=100.64.0.7 50000 100.64.0.1 22'")
    make_bin("claude", f'echo "$*" >> "{log}"')
    if timeout_name:
        make_bin(timeout_name, "exit 0")  # the MCP port "answers"
    subprocess.run([BASH, str(PW_AUTO)], env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
                   check=True)
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.parametrize("name", ["timeout", "gtimeout"])
def test_pw_autoregister_uses_timeout_or_gtimeout(name: str, bin_dir: Path, make_bin: MakeBin,
                                                  tmp_path: Path) -> None:
    log = _pw_autoregister(bin_dir, make_bin, tmp_path, name)
    assert "http://100.64.0.7:8931/mcp" in log


def test_pw_autoregister_skips_without_any_timeout(bin_dir: Path, make_bin: MakeBin,
                                                   tmp_path: Path) -> None:
    assert _pw_autoregister(bin_dir, make_bin, tmp_path, None) == ""


def test_scripts_parse_and_lint() -> None:
    for f in (PROBE, RESOURCES):
        assert subprocess.run(["sh", "-n", str(f)]).returncode == 0, f
    for f in (PW_AUTO, STATUSLINE):
        assert subprocess.run([BASH, "-n", str(f)]).returncode == 0, f
    if shutil.which("shellcheck"):
        res = subprocess.run(["shellcheck", "-S", "warning", str(PROBE), str(RESOURCES),
                              str(PW_AUTO)], capture_output=True, text=True)
        assert res.returncode == 0, res.stdout
