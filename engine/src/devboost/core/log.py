"""Thin loguru wrapper preserving the bash engine's info/ok/skip/error semantics."""

from __future__ import annotations

import sys

from loguru import logger

logger.remove()
logger.add(sys.stderr, format="{message}", level="INFO")


def info(msg: str) -> None:
    logger.opt(colors=True).info(msg)


def ok(msg: str) -> None:
    logger.opt(colors=True).info(f"<green>ok</green> {msg}")


def skip(msg: str) -> None:
    logger.opt(colors=True).info(f"<yellow>skip</yellow> {msg}")


def warn(msg: str) -> None:
    logger.opt(colors=True).warning(f"<yellow>warn</yellow> {msg}")


def error(msg: str) -> None:
    logger.opt(colors=True).error(f"<red>error</red> {msg}")
