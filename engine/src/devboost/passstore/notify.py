"""Notifications: ntfy (phone, optional) and the desktop's native notifier."""

from __future__ import annotations

import os
import re

from devboost.core.osinfo import OsInfo
from devboost.model import Ctx

#: C0/C1 control characters, zero-width marks and the bidi overrides/isolates that can
#: disguise text.
_UNSAFE = re.compile(
    "[\x00-\x1f\x7f-\x9f\u200b-\u200f\u061c\ufeff\u202a-\u202e\u2066-\u2069]"
)


def printable(text: str) -> str:
    """A remote-sourced string made safe to write to a terminal or log line: no control /
    invisible characters. No truncation, no markup handling — those are `clean`'s and the
    notifier's business respectively."""
    return _UNSAFE.sub("", text)


def clean(text: str, limit: int = 64) -> str:
    """A remote-sourced string (a record's name / os) made safe to show in a notification:
    no control / invisible characters, no leading `-` (never read as an option), at most
    *limit* chars. Markup escaping is the notifier's business (see `_native_argv`)."""
    return printable(text).strip().lstrip("-").strip()[:limit]


def _markup(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ntfy(ctx: Ctx, title: str, body: str, *, priority: str = "default") -> bool:
    """POST to $DEVBOOST_NTFY_URL (same topic claude-notify uses). Unset → no-op."""
    url = os.environ.get("DEVBOOST_NTFY_URL")
    if not url:
        return False
    argv = ["curl", "-fsS", "--max-time", "5", "-H", f"Title: {title}",
            "-H", f"Priority: {priority}", "-H", "Tags: key", "-d", body, url]
    return ctx.ex.run(argv).ok


#: AppleScript that takes the title and body as run-handler arguments: they are never
#: parsed as script text, so no quoting can break out of them (R1).
_OSASCRIPT = (
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "end run",
)


def _native_argv(os_info: OsInfo, title: str, body: str) -> list[str]:
    """macOS: osascript (title/body as argv); Linux: libnotify (the body is markup)."""
    if os_info.family == "macos":
        script = [arg for line in _OSASCRIPT for arg in ("-e", line)]
        return ["osascript", *script, title, body]
    return ["notify-send", "--app-name=devboost", title, _markup(body)]


def native(ctx: Ctx, title: str, body: str) -> bool:
    argv = _native_argv(ctx.os, title, body)
    if not ctx.ex.which(argv[0]):
        return False
    return ctx.ex.run(argv).ok
