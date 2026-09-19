"""Thin loguru wrapper preserving the bash engine's info/ok/skip/error semantics."""

from __future__ import annotations

import sys

from loguru import logger

logger.remove()
logger.add(sys.stderr, format="{message}", level="INFO")

# Messages are passed as format *arguments*: loguru colours only the format string, so text
# like `git clone <repo>` or a stray backslash is printed verbatim, never parsed as markup.


def info(msg: str) -> None:
    logger.opt(colors=True).info("{}", msg)


def ok(msg: str) -> None:
    logger.opt(colors=True).info("<green>ok</green> {}", msg)


def skip(msg: str) -> None:
    logger.opt(colors=True).info("<yellow>skip</yellow> {}", msg)


def warn(msg: str) -> None:
    logger.opt(colors=True).warning("<yellow>warn</yellow> {}", msg)


def error(msg: str) -> None:
    logger.opt(colors=True).error("<red>error</red> {}", msg)
