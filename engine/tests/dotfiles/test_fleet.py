from __future__ import annotations

import subprocess
from pathlib import Path

FLEET = (
    Path(__file__).resolve().parents[3] / "dotfiles" / "dot_local" / "bin" / "executable_fleet"
)


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(FLEET), *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
    )


def test_fleet_script_is_valid_bash() -> None:
    # `bash -n` parses without executing — catches syntax errors in the dispatcher.
    result = subprocess.run(["bash", "-n", str(FLEET)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_fleet_no_args_prints_usage_nonzero() -> None:
    result = _run([])
    assert result.returncode != 0
    assert "usage" in (result.stdout + result.stderr).lower()


def test_fleet_unknown_verb_errors() -> None:
    result = _run(["frobnicate"])
    assert result.returncode != 0
    assert "frobnicate" in (result.stdout + result.stderr).lower() or "usage" in (
        result.stdout + result.stderr
    ).lower()


def test_fleet_dev_without_brain_env_errors_cleanly() -> None:
    # DEVBOOST_BRAIN unset -> clean non-zero with a message, not a silent/obscure failure.
    result = _run(["dev"])
    assert result.returncode != 0
    assert "DEVBOOST_BRAIN" in (result.stdout + result.stderr)


def test_fleet_edge_without_edge_env_errors_cleanly() -> None:
    result = _run(["edge"])
    assert result.returncode != 0
    assert "DEVBOOST_EDGE" in (result.stdout + result.stderr)


def test_fleet_expose_rejects_non_numeric_port() -> None:
    result = _run(["expose", "8080; touch /tmp/pwned"], env={"DEVBOOST_BRAIN": "brain"})
    assert result.returncode != 0
    assert "number" in (result.stdout + result.stderr).lower()


def test_fleet_rejects_dash_prefixed_host() -> None:
    # A host value starting with '-' would be parsed by ssh as an option — must be refused.
    result = _run(["dev"], env={"DEVBOOST_BRAIN": "-oProxyCommand=evil"})
    assert result.returncode != 0
    assert "refused" in (result.stdout + result.stderr).lower()
