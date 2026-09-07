"""codex-mcp — register the google-docs MCP server in Codex (context7 dropped; plugin covers it)."""

from __future__ import annotations

import json

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.codex_code import CodexCode

# stdio server; secrets resolved from `pass` at runtime inside the bash wrapper.
CODEX_MCP_SERVERS: dict[str, list[str]] = {
    "google-docs": [
        "bash",
        "-lc",
        'export GOOGLE_CLIENT_ID="$(pass google-docs/dits_client_id)"; '
        'export GOOGLE_CLIENT_SECRET="$(pass google-docs/dits_client_secret)"; '
        "exec npx -y @a-bonus/google-docs-mcp",
    ],
}


@register
class CodexMcp(Module):
    name = "codex-mcp"
    category = "cli"
    description = "Register Codex MCP servers (google-docs)."
    requires = (CodexCode,)
    profiles = ("codex",)

    def _installed(self, ctx: Ctx) -> set[str]:
        if not ctx.ex.which("codex"):
            return set()
        res = ctx.ex.run(["codex", "mcp", "list", "--json"])
        if not res.ok:
            return set()
        try:
            data = json.loads(res.stdout)
        except ValueError:
            return set()
        if isinstance(data, list):
            return {
                e["name"] for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)
            }
        if isinstance(data, dict):
            return {k for k in data}
        return set()

    def verify(self, ctx: Ctx) -> bool:
        return set(CODEX_MCP_SERVERS).issubset(self._installed(ctx))

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("codex"):
            log.warn("codex-mcp: codex CLI not found — skipping MCP registration")
            return
        present = self._installed(ctx)
        for name, cmd in CODEX_MCP_SERVERS.items():
            if name in present:
                log.skip(f"codex-mcp: {name} already registered")
                continue
            res = ctx.ex.run(["codex", "mcp", "add", name, "--", *cmd])
            if not res.ok:
                log.warn(f"codex-mcp: failed to add {name}: {res.stderr.strip()}")
