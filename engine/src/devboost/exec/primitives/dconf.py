"""dconf primitive — load a dconf dump under a schema path (idempotent in effect)."""

from __future__ import annotations

from pathlib import Path

from devboost.model import Ctx


def load(ctx: Ctx, dump: Path, *, root: str = "/") -> None:
    ctx.ex.run(["dconf", "load", root], stdin=dump.read_text(encoding="utf-8"))
