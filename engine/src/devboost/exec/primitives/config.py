"""Config primitive: idempotent JSON merge + line-ensure, using stdlib for data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.model import Ctx


def json_merge(ctx: Ctx, path: str, patch: Mapping[str, Any]) -> None:
    p = Path(path)
    current: dict[str, Any] = {}
    if p.exists():
        current = json.loads(p.read_text(encoding="utf-8"))
    merged = {**current, **patch}
    if merged != current:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def ensure_line(ctx: Ctx, path: str, line: str) -> None:
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if line not in lines:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join([*lines, line]) + "\n", encoding="utf-8")
