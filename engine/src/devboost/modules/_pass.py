"""Reading secrets from `pass` without ever failing the run.

Until this device is approved (or when pass is absent), a read simply returns None and the
caller skips that one secret — the spec's "warn + skip, never fail".
"""

from __future__ import annotations

from devboost.core import log
from devboost.model import Ctx


def pass_show(ctx: Ctx, entry: str, *, who: str) -> str | None:
    if not ctx.ex.which("pass"):
        log.warn(f"{who}: pass not installed — skipping {entry}")
        return None
    res = ctx.ex.run(["pass", "show", entry])
    if not res.ok or not res.stdout.strip():
        log.warn(f"{who}: `pass show {entry}` unavailable (missing, or this device is not "
                 "approved yet — see `devboost pass status`) — skipping")
        return None
    return res.stdout


def pass_fields(text: str) -> dict[str, str]:
    """`key: value` lines of a pass entry (the first line, the password, is not a field)."""
    out: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep and key.strip():
            out[key.strip().lower()] = value.strip()
    return out


def pass_line(ctx: Ctx, entry: str, *, who: str) -> str | None:
    """The first line of a pass entry (its password / token), or None when unavailable."""
    out = pass_show(ctx, entry, who=who)
    line = out.splitlines()[0].strip() if out else ""
    return line or None
