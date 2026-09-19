"""``scripts/smoke-assert.sh`` — guest-side post-install checks (Task 6)."""

from __future__ import annotations

from pathlib import Path

from tests.scripts.conftest import StubPath, run_bash

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "smoke-assert.sh"


def _linux_env(stub_path: StubPath) -> dict[str, str]:
    stub_path.add("uname", "echo Linux")
    return stub_path.env()


def test_smoke_assert_all_pass(stub_path: StubPath) -> None:
    stub_path.add("devboost", "exit 0")
    stub_path.add("herdr", "echo 'herdr 0.9.1'")
    stub_path.add("glow", "exit 0")
    stub_path.add("bash", "exit 0")

    result = run_bash(SCRIPT, "macos", env=_linux_env(stub_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_smoke_assert_reports_each_failure(stub_path: StubPath) -> None:
    stub_path.add("devboost", "exit 0")
    stub_path.add("herdr", "echo 'herdr 0.9.0'")
    # no glow stub — not on PATH.
    stub_path.add("bash", "echo 'boot warning' >&2; exit 0")

    result = run_bash(SCRIPT, "macos", env=_linux_env(stub_path))

    assert result.returncode == 1
    assert "0.9.1" in result.stderr  # names what was wanted, not just what failed
    assert "glow" in result.stderr
    assert "bash -lic exit" in result.stderr
