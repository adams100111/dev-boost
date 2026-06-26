"""Config primitive: idempotent JSON merge + line-ensure, using stdlib for data."""

from __future__ import annotations

import json
import os
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


def comment_block(text: str, begin: str, end: str) -> str:
    """Prefix '# ' to each non-empty, not-already-commented line within [begin, end]."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line == begin:
            inside = True
            out.append(line)
        elif line == end:
            inside = False
            out.append(line)
        elif inside and line and not line.startswith("# "):
            out.append(f"# {line}")
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def write_kv(ctx: Ctx, path: str, key: str, value: str) -> None:
    """Ensure `key=value` in an ini-style file (replace-not-append). Privileged via tee."""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out: list[str] = []
    replaced = False
    for ln in lines:
        if ln.split("=", 1)[0] == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"{key}={value}")
    body = "\n".join(out) + "\n"
    # Direct write when we can (existing writable file, or a writable parent dir);
    # otherwise route a privileged write through the executor.
    if p.exists():
        writable = os.access(path, os.W_OK)
    else:
        writable = os.access(p.parent, os.W_OK)
    if writable:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    else:
        ctx.ex.run(["tee", path], sudo=True, stdin=body)
