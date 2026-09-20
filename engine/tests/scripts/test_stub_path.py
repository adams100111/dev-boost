"""Proves the ``stub_path``/``run_bash`` fixture pair: a stubbed command on PATH shadows
the real tool of the same name, which is what every other script test relies on."""

from __future__ import annotations

from pathlib import Path

from tests.scripts.conftest import StubPath, run_bash


def test_stub_path_shadows_uname(stub_path: StubPath) -> None:
    stub_path.add("uname", "echo Darwin")

    result = run_bash(Path("uname"), env=stub_path.env())

    assert result.returncode == 0
    assert result.stdout.strip() == "Darwin"
