"""mise primitive — pin a tool globally, and read/write mise's own settings."""

from __future__ import annotations

from devboost.model import Ctx


def use_global(ctx: Ctx, spec: str) -> None:
    """`mise use -g <spec>` — e.g. node@22, java@21, npm:@anthropic-ai/claude-code."""
    ctx.ex.run(["mise", "use", "-g", spec])


def setting_get(ctx: Ctx, key: str) -> str | None:
    """The effective value of a mise setting, or None when it is unset."""
    res = ctx.ex.run(["mise", "settings", "get", key])
    if not res.ok:
        return None
    value = res.stdout.strip()
    return value or None


def setting_set(ctx: Ctx, key: str, value: str) -> None:
    """`mise settings set <key> <value>` — mise edits its own config.toml in place,
    so the `[tools]` pins written by `use_global` are preserved."""
    ctx.ex.run(["mise", "settings", "set", key, value])
