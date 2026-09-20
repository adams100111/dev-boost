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
    """``uname`` reports Linux even for the ``macos`` profile argument: smoke-assert.sh
    branches on ``uname -s`` only to pick the login shell to probe (zsh on Darwin, bash
    elsewhere), and on nothing else — the profiles are just passed to ``devboost verify``.
    Linux keeps the probe on the ``bash`` stub these tests control."""
    stub_path.add("uname", "echo Linux")
    return stub_path.env()


def test_smoke_assert_all_pass(stub_path: StubPath) -> None:
    stub_path.add("devboost", "exit 0")
    stub_path.add("herdr", "echo 'herdr 0.9.1'")
    stub_path.add("glow", "exit 0")
    stub_path.add("bash", "exit 0")

    result = run_bash(SCRIPT, "macos", env=_linux_env(stub_path))

    assert result.returncode == 0, result.stderr
    # A pass says so: a silent success reads exactly like a smoke that never ran, and a
    # rehearsal log is the only record that it did.
    assert result.stdout == "smoke-assert: all checks passed (macos)\n"
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


#: What `bash -lic exit` prints on stderr with no controlling tty (a CI step, `sudo -u`,
#: `tart exec`), whatever the rc files do — bash 5 on Linux, then bash 3.2's form.
TTY_NOISE = (
    "bash: cannot set terminal process group (145): Inappropriate ioctl for device\n"
    "bash: no job control in this shell\n"
    "logout\n"
)


def _all_green(stub_path: StubPath) -> None:
    stub_path.add("devboost", "exit 0")
    stub_path.add("herdr", "echo 'herdr 0.9.1'")
    stub_path.add("glow", "exit 0")


def test_smoke_assert_ignores_no_tty_job_control_noise(stub_path: StubPath) -> None:
    """A-I3: a healthy install must pass in a tty-less CI step."""
    _all_green(stub_path)
    stub_path.add("bash", f"printf '{TTY_NOISE}' >&2; exit 0")

    result = run_bash(SCRIPT, "cli", "ghostty", env=_linux_env(stub_path))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_smoke_assert_still_reports_a_real_shell_error(stub_path: StubPath) -> None:
    """…while a genuine rc-file error amid that noise still fails, and is the only thing
    reported."""
    _all_green(stub_path)
    stub_path.add(
        "bash", f"printf '{TTY_NOISE}' >&2; echo 'bashrc: line 3: foo: not found' >&2"
    )

    result = run_bash(SCRIPT, "cli", env=_linux_env(stub_path))

    assert result.returncode == 1
    assert "bashrc: line 3: foo: not found" in result.stderr
    assert "no job control" not in result.stderr


def test_smoke_assert_names_a_missing_devboost(stub_path: StubPath) -> None:
    """A-I3: devboost not on PATH is reported as exactly that, once."""
    stub_path.add("herdr", "echo 'herdr 0.9.1'")
    stub_path.add("glow", "exit 0")
    stub_path.add("bash", "exit 0")

    result = run_bash(SCRIPT, "cli", env=_linux_env(stub_path))

    assert result.returncode == 1
    assert "smoke-assert: FAIL: devboost not on PATH" in result.stderr
    assert "devboost verify" not in result.stderr


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
    fixtures/kickstart-smoke-job.yml; the one deliberate change since is its runner,
    ubuntu-22.04 → ubuntu-24.04 (the 22.04 image's deprecation, ruling C-M6-R1)."""
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


def test_vm_smoke_runs_smoke_assert_with_devboost_on_path() -> None:
    """A-I3: the source-installed devboost lives in engine/.venv, so every smoke-assert
    invocation runs under `uv run` from engine/ — never a bare `sh scripts/…`."""
    text = _vm_smoke_text()
    calls = [ln for ln in text.splitlines() if "smoke-assert.sh cli ghostty\"" in ln]
    assert len(calls) == 2, calls
    for line in calls:
        assert "/engine' && uv run sh ../scripts/smoke-assert.sh cli ghostty" in line
