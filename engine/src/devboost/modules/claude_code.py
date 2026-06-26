"""claude-code — install the Claude Code CLI via npm (node provisioned through mise)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import mise
from devboost.model import Ctx, Module
from devboost.modules.mise import Mise


@register
class ClaudeCode(Module):
    name = "claude-code"
    category = "cli"
    description = "Claude Code CLI (npm; node via mise)."
    requires = (Mise,)
    profiles = ("cli",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("claude")

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("node"):
            mise.use_global(ctx, "node@lts")
        ctx.ex.run(["npm", "install", "-g", "@anthropic-ai/claude-code"])
