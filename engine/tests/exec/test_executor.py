from __future__ import annotations

import os

from devboost.exec.executor import FakeExecutor, RealExecutor, Result, _prepend_mise_dirs


def test_fake_records_calls_and_sudo_prefix() -> None:
    ex = FakeExecutor()
    ex.run(["dnf", "install", "-y", "ripgrep"], sudo=True)
    ex.run(["rpm", "-q", "ripgrep"])
    assert ex.calls == [
        ["sudo", "dnf", "install", "-y", "ripgrep"],
        ["rpm", "-q", "ripgrep"],
    ]


def test_fake_scripts_and_present() -> None:
    ex = FakeExecutor(scripts={"rpm": Result(1)}, present={"rg"})
    assert ex.run(["rpm", "-q", "x"]).code == 1
    assert ex.run(["true"]).ok
    assert ex.which("rg") is True
    assert ex.which("nope") is False


def test_real_which_finds_python() -> None:
    assert RealExecutor().which("python3") is True
    assert RealExecutor().which("definitely-not-a-real-binary-xyz") is False


def test_prepend_mise_dirs_adds_shims_before_existing_path() -> None:
    """mise shims and ~/.local/bin must appear before existing PATH entries."""
    original = "/usr/bin:/usr/local/bin"
    augmented = _prepend_mise_dirs(original)
    parts = augmented.split(os.pathsep)
    shims_idx = next((i for i, p in enumerate(parts) if "mise" in p and "shims" in p), None)
    usr_bin_idx = next((i for i, p in enumerate(parts) if p == "/usr/bin"), None)
    assert shims_idx is not None, "mise shims dir not found in augmented PATH"
    assert usr_bin_idx is not None
    assert shims_idx < usr_bin_idx, "mise shims must come before /usr/bin"


def test_prepend_mise_dirs_is_idempotent() -> None:
    """Calling _prepend_mise_dirs twice must not duplicate dirs."""
    path = _prepend_mise_dirs("/usr/bin")
    twice = _prepend_mise_dirs(path)
    parts_once = path.split(os.pathsep)
    parts_twice = twice.split(os.pathsep)
    assert parts_once == parts_twice


def test_prepend_mise_dirs_handles_empty_path() -> None:
    result = _prepend_mise_dirs("")
    assert "mise" in result or ".local/bin" in result


def test_real_executor_run_has_mise_on_path() -> None:
    """RealExecutor.run passes an env that includes mise shims in PATH."""
    ex = RealExecutor()
    result = ex.run(["sh", "-c", "echo $PATH"])
    assert result.ok
    assert "mise" in result.stdout or ".local" in result.stdout
