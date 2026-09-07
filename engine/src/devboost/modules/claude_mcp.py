"""claude-mcp — register the user-global MCP servers (google-docs, fathom)."""

from __future__ import annotations

from devboost.core import log
from devboost.core.registry import register
from devboost.exec.executor import Result
from devboost.model import Ctx, Module
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.shell import Dotfiles

# google-docs: public npm server; secrets resolved from `pass` at runtime in a login shell.
# fathom: remote server via mcp-remote; auth is interactive OAuth, no secret in config.
MCP_SERVERS: dict[str, str] = {
    "google-docs": (
        '{"type":"stdio","command":"bash","args":["-lc",'
        '"export GOOGLE_CLIENT_ID=\\"$(pass google-docs/dits_client_id)\\"; '
        'export GOOGLE_CLIENT_SECRET=\\"$(pass google-docs/dits_client_secret)\\"; '
        'exec npx -y @a-bonus/google-docs-mcp"]}'
    ),
    "fathom": (
        '{"type":"stdio","command":"npx","args":'
        '["-y","mcp-remote@latest","https://api.fathom.ai/mcp"]}'
    ),
}


@register
class ClaudeMcp(Module):
    name = "claude-mcp"
    category = "cli"
    description = "Register user-global MCP servers (google-docs, fathom)."
    requires = (ClaudeCode, Dotfiles)
    profiles = ("cli",)

    def _installed(self, ctx: Ctx) -> str:
        if not ctx.ex.which("claude"):
            return ""
        res: Result = ctx.ex.run(["claude", "mcp", "list"])
        return res.stdout if res.ok else ""

    def verify(self, ctx: Ctx) -> bool:
        listed = self._installed(ctx)
        return all(name in listed for name in MCP_SERVERS)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("claude"):
            log.warn("claude-mcp: claude CLI not found — skipping MCP registration")
            return
        listed = self._installed(ctx)
        for name, spec in MCP_SERVERS.items():
            if name in listed:
                log.skip(f"claude-mcp: {name} already registered")
                continue
            res = ctx.ex.run(["claude", "mcp", "add-json", name, spec, "--scope", "user"])
            if not res.ok:
                log.warn(f"claude-mcp: failed to add {name}: {res.stderr.strip()}")
