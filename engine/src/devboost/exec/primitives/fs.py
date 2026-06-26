"""Filesystem primitive. Reads are in-process; writes go through the executor so a
privileged or previewed write is uniform and testable.
"""

from __future__ import annotations

from pathlib import Path

from devboost.model import Ctx


def exists(ctx: Ctx, path: str) -> bool:
    return Path(path).exists()


def write(ctx: Ctx, path: str, content: str, *, sudo: bool = False) -> None:
    if sudo:
        ctx.ex.run(["tee", path], sudo=True, stdin=content)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
