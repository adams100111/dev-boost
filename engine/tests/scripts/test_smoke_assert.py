"""``scripts/smoke-assert.sh`` — guest-side post-install checks (Task 6), plus (Task 7) plain
text/regex assertions on `.github/workflows/vm-smoke.yml`'s Linux legs. No YAML parsing —
these are simple substring/regex checks over the file text, matching the pattern lane D
established for `test_workflows.py`."""

from __future__ import annotations

import re
from pathlib import Path

from tests.scripts.conftest import StubPath, run_bash

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "smoke-assert.sh"
VM_SMOKE = ROOT / ".github" / "workflows" / "vm-smoke.yml"


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


# --- Task 7: the linux-smoke job in vm-smoke.yml --------------------------------------


def _vm_smoke_text() -> str:
    return VM_SMOKE.read_text(encoding="utf-8")


def test_vm_smoke_has_linux_legs() -> None:
    text = _vm_smoke_text()
    assert "linux-smoke:" in text
    assert "continue-on-error: true" in text
    assert "fedora:44" in text
    assert "archlinux:latest" in text
    # the ubuntu-host leg runs directly on the runner (no container), matched by name+runner.
    assert re.search(r"name:\s*ubuntu-host", text)
    assert "ubuntu-24.04" in text


def test_vm_smoke_asserts_ghostty_sources() -> None:
    text = _vm_smoke_text()
    assert "scottames/ghostty" in text
    assert "snap list ghostty" in text
    assert "pacman -Q ghostty" in text


def test_kickstart_job_unchanged() -> None:
    """The pre-existing `kickstart-smoke` job must stay byte-identical — Task 7 only adds a
    new job, never touches this one. Snapshot taken at T0 (pre-Task-7 file), in
    fixtures/kickstart-smoke-job.yml."""
    fixture = Path(__file__).parent / "fixtures" / "kickstart-smoke-job.yml"
    expected = fixture.read_text(encoding="utf-8")

    text = _vm_smoke_text()
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.strip() == "kickstart-smoke:")
    # The job block runs from its header up to (not including) whatever comes next: a blank
    # line followed by a comment/job-key line, a bare top-level key, or EOF.
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue  # blank line inside the block (none currently, but don't stop on one)
        if re.match(r"^ {2}\S", lines[i]) and (
            stripped.startswith("#") or re.match(r"^[A-Za-z0-9_-]+:\s*$", stripped)
        ):
            end = i
            break
        if not lines[i].startswith(" "):
            end = i
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    actual = "".join(lines[start:end])

    assert actual.rstrip("\n") == expected.rstrip("\n")
