"""``scripts/vm-test-macos.sh`` — drives tart VMs to rehearse the macOS `curl | bash` flow
(Task 6). Every test runs the real script under a stubbed PATH; nothing here ever boots,
clones or pulls a real tart VM — the ``--dry-run`` argv preview is the thing under test,
plus the host/tart preflight guards that run before any tart command."""

from __future__ import annotations

import shutil
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


def test_dry_run_run_local_sets_release_base(stub_path: StubPath, tmp_path: Path) -> None:
    local_dir = tmp_path / "dist"
    local_dir.mkdir()
    (local_dir / "checksums-darwin-arm64.txt").write_text("deadbeef  devboost-darwin-arm64\n")
    (local_dir / "devboost-darwin-arm64").write_text("binary\n")

    out = _run("--dry-run", "run", "--local", str(local_dir), env=_darwin_arm64(stub_path))

    assert "--dir=dist:" in out
    assert "DEVBOOST_RELEASE_BASE=file://" in out


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
    import subprocess

    for f in (SCRIPT, SMOKE_ASSERT):
        res = subprocess.run(["shellcheck", "-x", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, res.stdout
