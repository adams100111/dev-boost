"""codex-code — install the OpenAI Codex CLI (standalone binary; self-updating)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import mise
from devboost.model import Ctx, Module
from devboost.modules.mise import Mise


@register
class CodexCode(Module):
    name = "codex-code"
    category = "cli"
    description = "OpenAI Codex CLI (standalone binary; self-updating via `codex update`)."
    requires = (Mise,)  # node for `npx skills`
    profiles = ("codex",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("codex")

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("node"):
            mise.use_global(ctx, "node@lts")
        # Official standalone installer → ~/.codex/packages/standalone, symlinked onto PATH.
        ctx.ex.run(["sh", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"])
