"""Shared fixture for shell-script tests: a directory of hermetic command stubs, plus a
helper that sources a real script and calls one of its functions (or runs a bare command)
under that stubbed PATH. No test here or in a script test that reuses this fixture ever
reaches a real external tool (uname, brew, sw_vers, tmutil, ...) or the real HOME."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


class StubPath:
    """A directory of ``#!/bin/sh`` command stubs, and the env a run needs to see only them."""

    def __init__(self, stubdir: Path, home: Path) -> None:
        self._stubdir = stubdir
        self._home = home

    def add(self, name: str, script: str) -> Path:
        """Write an executable ``#!/bin/sh`` stub named *name* that runs *script*."""
        stub = self._stubdir / name
        stub.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
        stub.chmod(0o755)
        return stub

    def env(self, **extra: str) -> dict[str, str]:
        """PATH resolving to the stub dir before the real (read-only) system dirs, a tmp
        HOME, and any *extra* vars a script under test needs."""
        return {
            "PATH": f"{self._stubdir}:/usr/bin:/bin",
            "HOME": str(self._home),
            **extra,
        }


@pytest.fixture
def stub_path(tmp_path: Path) -> StubPath:
    stubdir = tmp_path / "stubs"
    stubdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    return StubPath(stubdir, home)


def run_bash(
    script: Path,
    *args: str,
    env: dict[str, str],
    source_fn: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run *script* under bash.

    With *source_fn*, source *script* then call that function with *args: ``bash -c
    'source <script>; <source_fn> "$@"'``. Without it, run *script* itself with *args* —
    a bare name (no slash) is resolved against *env*'s PATH, so a stub shadows the real
    tool of the same name.
    """
    if source_fn is not None:
        command = ["bash", "-c", f'source "{script}"; {source_fn} "$@"', "bash", *args]
    else:
        command = [str(script), *args]
    return subprocess.run(command, env=env, capture_output=True, text=True, check=False)
