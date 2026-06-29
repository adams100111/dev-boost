"""CLI test fixtures — reroutes loguru through the live sys.stderr so CliRunner captures it."""

from __future__ import annotations

import sys

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def _loguru_dynamic_stderr() -> None:
    """Remove the module-load-time stderr sink and add a dynamic one.

    loguru's default sink captures the ``sys.stderr`` *object* at import time.  When
    typer's CliRunner runs it replaces ``sys.stderr`` in the ``sys`` module, but loguru
    still writes to the original file object, bypassing the runner's capture.  This
    fixture replaces the fixed sink with a callable lambda that dereferences
    ``sys.stderr`` at write time, so CliRunner output lands in ``result.output``.
    """
    logger.remove()
    logger.add(lambda msg: sys.stderr.write(msg), format="{message}", level="INFO")
    yield
    logger.remove()
    logger.add(sys.stderr, format="{message}", level="INFO")
