"""codex-plugins — register Codex marketplaces + install enabled plugins (reuses the claude set)."""

from __future__ import annotations

import json

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_plugins import ENABLED_PLUGINS
from devboost.modules.codex_code import CodexCode
from devboost.modules.secrets import Secrets

# marketplace name → source (owner/repo). clickup-flow was a local path → github for portability.
CODEX_MARKETPLACES: dict[str, str] = {
    "claude-plugins-official": "anthropics/claude-plugins-official",
    "qa-e2e-pilot": "adams100111/qa-e2e-pilot",
    "wave-pilot": "adams100111/wave-pilot",
    "ui-ux-pro-max-skill": "nextlevelbuilder/ui-ux-pro-max-skill",
    "clickup-flow-marketplace": "adams100111/clickup-flow",
}


@register
class CodexPlugins(Module):
    name = "codex-plugins"
    category = "cli"
    description = "Register Codex marketplaces + install enabled plugins."
    requires = (CodexCode, Secrets)  # Secrets → git creds for the private clickup-flow marketplace
    profiles = ("codex",)

    def _codex_json(self, ctx: Ctx, *args: str) -> object:
        res = ctx.ex.run(["codex", *args])
        if not res.ok:
            return None
        try:
            return json.loads(res.stdout)
        except ValueError:
            return None

    def _installed_marketplaces(self, ctx: Ctx) -> str:
        res = ctx.ex.run(["codex", "plugin", "marketplace", "list"])
        return res.stdout if res.ok else ""

    def _installed_plugins(self, ctx: Ctx) -> set[str]:
        data = self._codex_json(ctx, "plugin", "list", "--available", "--json")
        names: set[str] = set()
        if isinstance(data, list):
            for e in data:
                if isinstance(e, dict) and e.get("installed") and isinstance(e.get("name"), str):
                    names.add(e["name"])
        return names

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("codex"):
            return False
        installed = self._installed_plugins(ctx)
        return all(p.split("@", 1)[0] in installed for p in ENABLED_PLUGINS)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("codex"):
            log.warn("codex-plugins: codex CLI not found — skipping")
            return
        markets = self._installed_marketplaces(ctx)
        for name, source in CODEX_MARKETPLACES.items():
            if name in markets:
                log.skip(f"codex-plugins: marketplace {name} already configured")
                continue
            res = ctx.ex.run(["codex", "plugin", "marketplace", "add", source])
            if not res.ok:
                log.warn(f"codex-plugins: marketplace add {source} failed: {res.stderr.strip()}")
        installed = self._installed_plugins(ctx)
        for plugin in ENABLED_PLUGINS:
            if plugin.split("@", 1)[0] in installed:
                log.skip(f"codex-plugins: {plugin} already installed")
                continue
            res = ctx.ex.run(["codex", "plugin", "add", plugin, "--json"])
            if not res.ok:
                log.warn(f"codex-plugins: install {plugin} failed: {res.stderr.strip()}")
