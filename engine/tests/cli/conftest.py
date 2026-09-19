"""CLI test fixtures — reroutes loguru through the live sys.stderr so CliRunner captures it."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger


def _write_stderr(msg: str) -> None:
    sys.stderr.write(msg)


@pytest.fixture(autouse=True)
def _hermetic_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let doctor look at the developer's real ~/.password-store."""
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "pass-store"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)


@pytest.fixture(autouse=True)
def _loguru_dynamic_stderr() -> Iterator[None]:
    """Remove the module-load-time stderr sink and add a dynamic one.

    loguru's default sink captures the ``sys.stderr`` *object* at import time.  When
    typer's CliRunner runs it replaces ``sys.stderr`` in the ``sys`` module, but loguru
    still writes to the original file object, bypassing the runner's capture.  This
    fixture replaces the fixed sink with a callable lambda that dereferences
    ``sys.stderr`` at write time, so CliRunner output lands in ``result.output``.
    """
    logger.remove()
    logger.add(_write_stderr, format="{message}", level="INFO")
    yield
    logger.remove()
    logger.add(sys.stderr, format="{message}", level="INFO")
