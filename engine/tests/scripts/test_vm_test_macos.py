"""``scripts/vm-test-macos.sh`` — drives tart VMs to rehearse the macOS `curl | bash` flow
(Task 6). Every test runs the real script under a stubbed PATH; nothing here ever boots,
clones or pulls a real tart VM — the ``--dry-run`` argv preview is the thing under test,
plus the host/tart preflight guards that run before any tart command."""

from __future__ import annotations

import shutil
import subprocess
import urllib.parse
from pathlib import Path

import pytest

from tests.scripts.conftest import StubPath, run_bash

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "vm-test-macos.sh"
SMOKE_ASSERT = ROOT / "scripts" / "smoke-assert.sh"
BASH = shutil.which("bash") or "bash"


def _darwin_arm64(stub_path: StubPath) -> dict[str, str]:
    """A hermetic env whose ``uname`` always reports an Apple Silicon Mac, regardless of
    what this test happens to actually run on (Global Constraints: never read the host OS)."""
    stub_path.add("uname", 'case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; esac')
    return stub_path.env()


def _run(*args: str, env: dict[str, str]) -> str:
    result = run_bash(SCRIPT, *args, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_dry_run_create_27_argv(stub_path: StubPath) -> None:
    out = _run("--dry-run", "create", "--os", "27", env=_darwin_arm64(stub_path))
    assert out.splitlines() == [
        "+ tart clone ghcr.io/cirruslabs/macos-golden-gate-base:latest devboost-mac27",
        "+ tart set devboost-mac27 --cpu 4 --memory 8192 --disk-size 80",
    ]


def test_dry_run_create_26_argv(stub_path: StubPath) -> None:
    out = _run("--dry-run", "create", "--os", "26", env=_darwin_arm64(stub_path))
    assert out.splitlines() == [
        "+ tart clone ghcr.io/cirruslabs/macos-tahoe-base:latest devboost-mac26",
        "+ tart set devboost-mac26 --cpu 4 --memory 8192 --disk-size 80",
    ]


def test_dry_run_snapshot_revert_destroy_argv(stub_path: StubPath) -> None:
    env = _darwin_arm64(stub_path)

    snap = _run("--dry-run", "snapshot", "clean", env=env)
    assert snap.splitlines() == [
        "+ tart stop devboost-mac27",
        "+ tart clone devboost-mac27 devboost-mac27--clean",
    ]

    revert = _run("--dry-run", "revert", "clean", env=env)
    assert revert.splitlines() == [
        "+ tart stop devboost-mac27",
        "+ tart delete devboost-mac27",
        "+ tart clone devboost-mac27--clean devboost-mac27",
    ]

    destroy = _run("--dry-run", "destroy", env=env)
    assert destroy.splitlines() == [
        "+ tart stop devboost-mac27",
        "+ tart delete devboost-mac27",
    ]


GUEST = "/Volumes/My Shared Files/dist"
GUEST_URL = "file:///Volumes/My%20Shared%20Files/dist"


def _local_dist(tmp_path: Path) -> Path:
    local_dir = tmp_path / "dist"
    local_dir.mkdir()
    (local_dir / "checksums-darwin-arm64.txt").write_text("deadbeef  devboost-darwin-arm64\n")
    (local_dir / "devboost-darwin-arm64").write_text("binary\n")
    return local_dir


def test_dry_run_run_local_exact_guest_commands(stub_path: StubPath, tmp_path: Path) -> None:
    """C1: the file:// base is percent-encoded (curl rejects raw spaces). C2: get.sh is a
    FILE operand, so its args are the profiles — no `-s --`. I1: the smoke runs in a
    second exec, a fresh zsh login shell started after the install."""
    local_dir = _local_dist(tmp_path)
    mktemp_log = tmp_path / "mktemp.log"
    stub_path.add("mktemp", f'echo called >> "{mktemp_log}"; exit 1')
    out = _run("--dry-run", "run", "--local", str(local_dir), env=_darwin_arm64(stub_path))
    assert out.splitlines() == [
        "+ tart run --no-graphics --dir=dist:<staging-dir> devboost-mac27",
        "+ tart ip --wait 120 devboost-mac27",
        f"+ tart exec -i devboost-mac27 /bin/bash -lc 'DEVBOOST_RELEASE_BASE={GUEST_URL} "
        f'bash "{GUEST}/get.sh" macos\'',
        f"+ tart exec -i devboost-mac27 /bin/zsh -lc 'sh \"{GUEST}/smoke-assert.sh\" macos'",
    ]
    assert " -s " not in out
    assert not mktemp_log.exists(), "a preview must stage nothing"


def test_dry_run_run_remote_exact_guest_commands(stub_path: StubPath) -> None:
    out = _run("--dry-run", "run", "--profiles", "macos cli", env=_darwin_arm64(stub_path))
    raw = "https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts"
    assert out.splitlines() == [
        "+ tart run --no-graphics devboost-mac27",
        "+ tart ip --wait 120 devboost-mac27",
        f"+ tart exec -i devboost-mac27 /bin/bash -lc 'curl -fsSL {raw}/smoke-assert.sh "
        f'-o "$HOME/smoke-assert.sh" && curl -fsSL {raw}/get.sh | bash -s -- macos cli\'',
        "+ tart exec -i devboost-mac27 /bin/zsh -lc 'sh \"$HOME/smoke-assert.sh\" macos cli'",
    ]


def test_local_install_command_really_runs(stub_path: StubPath, tmp_path: Path) -> None:
    """Execute the rehearsal's exact install command (guest share path swapped for a local
    dir that ALSO contains spaces) with the real curl and the real get.sh: it must verify,
    install and exec `devboost install macos` — not die on the URL (C1) or pass `-s --`
    through as profiles (C2)."""
    if shutil.which("curl") is None:
        pytest.skip("curl is not installed")
    from tests.scripts.test_get_sh import _make_harness

    local_dir = _local_dist(tmp_path)
    out = _run(
        "--dry-run", "run", "--local", str(local_dir), env=_darwin_arm64(stub_path)
    )
    line = next(ln for ln in out.splitlines() if "/bin/bash -lc" in ln)
    install_cmd = line.split("/bin/bash -lc ", 1)[1][1:-1]  # strip the quoting

    h = _make_harness(
        stub_path,
        tmp_path,
        real_curl=True,
        canned_name="Volumes/My Shared Files/dist",
    )
    shutil.copy2(ROOT / "scripts" / "get.sh", h.canned / "get.sh")
    share = str(h.canned)
    install_cmd = install_cmd.replace(GUEST_URL, "file://" + urllib.parse.quote(share))
    install_cmd = install_cmd.replace(GUEST, share)
    assert "%20" in install_cmd

    proc = subprocess.run(
        [BASH, "-c", install_cmd], env=h.env, capture_output=True, text=True, check=False
    )

    assert proc.returncode == 0, proc.stderr
    assert h.exec_lines()[0] == "args=install macos"


def test_refuses_linux_host(stub_path: StubPath) -> None:
    stub_path.add("uname", 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac')

    result = run_bash(SCRIPT, "list", env=stub_path.env())

    assert result.returncode == 1
    assert "requires a Darwin host" in result.stderr


def test_missing_tart_message(stub_path: StubPath) -> None:
    # Darwin/arm64 (so the host guard passes) but no `tart` stub on PATH, and NOT --dry-run.
    result = run_bash(SCRIPT, "list", env=_darwin_arm64(stub_path))

    assert result.returncode == 1
    assert (
        "vm-test-macos: missing 'tart' — install with: brew install cirruslabs/cli/tart"
        in result.stderr
    )


def test_local_without_the_binary_refused(stub_path: StubPath, tmp_path: Path) -> None:
    local_dir = tmp_path / "dist"
    local_dir.mkdir()
    (local_dir / "checksums-darwin-arm64.txt").write_text("deadbeef  devboost-darwin-arm64\n")
    result = run_bash(
        SCRIPT, "--dry-run", "run", "--local", str(local_dir), env=_darwin_arm64(stub_path)
    )
    assert result.returncode == 1
    assert "missing devboost-darwin-arm64" in result.stderr


def test_local_without_checksums_refused(stub_path: StubPath, tmp_path: Path) -> None:
    empty_dir = tmp_path / "dist"
    empty_dir.mkdir()

    result = run_bash(
        SCRIPT, "--dry-run", "run", "--local", str(empty_dir), env=_darwin_arm64(stub_path)
    )

    assert result.returncode == 1
    assert "missing checksums.txt" in result.stderr


def test_scripts_shellcheck_clean() -> None:
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    for f in (SCRIPT, SMOKE_ASSERT):
        res = subprocess.run(["shellcheck", "-x", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, res.stdout
