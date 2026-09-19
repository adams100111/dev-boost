"""Reading secrets from `pass` without ever failing the run.

Until this device is approved (or when pass is absent), a read simply returns None and the
caller skips that one secret — the spec's "warn + skip, never fail".
"""

from __future__ import annotations

import os

from devboost.core import log
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src

#: Unattended reads never open a passphrase prompt nobody answers (pinentry-mac is a GUI
#: dialog; R12): gpg still uses a cached passphrase, and without one it fails at once.
NO_PINENTRY = "--pinentry-mode error"


def _env(interactive: bool) -> dict[str, str] | None:
    if interactive:
        return None
    opts = os.environ.get("PASSWORD_STORE_GPG_OPTS", "").strip()
    return {"PASSWORD_STORE_GPG_OPTS": f"{opts} {NO_PINENTRY}".strip()}


def pass_show(ctx: Ctx, entry: str, *, who: str) -> str | None:
    if not ctx.ex.which("pass"):
        log.skip(f"{who}: pass not installed — skipping {entry}")
        return None
    interactive = creds_src.is_interactive()
    res = ctx.ex.run(["pass", "show", entry], env=_env(interactive))
    if not res.ok or not res.stdout.strip():
        hint = "" if interactive else (
            ", or its passphrase is not cached — unlock once in a terminal: "
            f"`pass show {entry}`")
        log.warn(f"{who}: `pass show {entry}` unavailable (missing, or this device is not "
                 f"approved yet — see `devboost pass status`{hint}) — skipping")
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
