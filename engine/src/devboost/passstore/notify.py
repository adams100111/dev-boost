"""Notifications: ntfy (phone, optional) and the desktop's native notifier."""

from __future__ import annotations

import os
import re

from devboost.core.osinfo import OsInfo
from devboost.model import Ctx

#: C0/C1 control characters and the bidi overrides/isolates that can disguise text.
_UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def clean(text: str, limit: int = 64) -> str:
    """A remote-sourced string (a record's name / os) made safe to show in a notification:
    no control characters, no leading `-` (never read as an option), at most *limit* chars."""
    return _UNSAFE.sub("", text).strip().lstrip("-").strip()[:limit]


def ntfy(ctx: Ctx, title: str, body: str, *, priority: str = "default") -> bool:
    """POST to $DEVBOOST_NTFY_URL (same topic claude-notify uses). Unset → no-op."""
    url = os.environ.get("DEVBOOST_NTFY_URL")
    if not url:
        return False
    argv = ["curl", "-fsS", "--max-time", "5", "-H", f"Title: {title}",
            "-H", f"Priority: {priority}", "-H", "Tags: key", "-d", body, url]
    return ctx.ex.run(argv).ok


def _native_argv(os_info: OsInfo, title: str, body: str) -> list[str] | None:
    """P2 seam: macOS returns an osascript argv here; Linux uses libnotify."""
    if os_info.family == "macos":
        return None
    return ["notify-send", "--app-name=devboost", title, body]


def native(ctx: Ctx, title: str, body: str) -> bool:
    argv = _native_argv(ctx.os, title, body)
    if argv is None or not ctx.ex.which(argv[0]):
        return False
    return ctx.ex.run(argv).ok
