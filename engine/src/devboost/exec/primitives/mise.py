"""mise primitive — pin a tool globally in the user's mise config."""

from __future__ import annotations

from devboost.model import Ctx


def use_global(ctx: Ctx, spec: str) -> None:
    """`mise use -g <spec>` — e.g. node@22, java@21, npm:@anthropic-ai/claude-code."""
    ctx.ex.run(["mise", "use", "-g", spec])
