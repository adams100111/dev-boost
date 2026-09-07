"""claude-plugins — register marketplaces, install enabled plugins, resolve CLICKUP token."""

from __future__ import annotations

import json
import os
from pathlib import Path

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.optional import PassStore
from devboost.modules.secrets import Secrets
from devboost.modules.shell import Dotfiles

MARKETPLACES: dict[str, dict[str, str]] = {
    "claude-plugins-official": {"source": "github", "repo": "anthropics/claude-plugins-official"},
    "qa-e2e-pilot": {"source": "github", "repo": "adams100111/qa-e2e-pilot"},
    "wave-pilot": {"source": "github", "repo": "adams100111/wave-pilot"},
    "ui-ux-pro-max-skill": {"source": "github", "repo": "nextlevelbuilder/ui-ux-pro-max-skill"},
    "aspire-skills": {"source": "github", "repo": "microsoft/aspire-skills"},
    "zoom-skills": {"source": "github", "repo": "zoom/skills"},
    # was a machine-local `directory` source — converted to the private github repo for portability
    "clickup-flow-marketplace": {"source": "github", "repo": "adams100111/clickup-flow"},
}

ENABLED_PLUGINS: tuple[str, ...] = (
    "claude-md-management@claude-plugins-official",
    "code-review@claude-plugins-official",
    "code-simplifier@claude-plugins-official",
    "context7@claude-plugins-official",
    "csharp-lsp@claude-plugins-official",
    "figma@claude-plugins-official",
    "frontend-design@claude-plugins-official",
    "github@claude-plugins-official",
    "php-lsp@claude-plugins-official",
    "playwright@claude-plugins-official",
    "pyright-lsp@claude-plugins-official",
    "typescript-lsp@claude-plugins-official",
    "superpowers@claude-plugins-official",
    "vercel@claude-plugins-official",
    "qa-e2e-pilot@qa-e2e-pilot",
    "wave-pilot@wave-pilot",
    "ui-ux-pro-max@ui-ux-pro-max-skill",
    "clickup-flow@clickup-flow-marketplace",
)


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class ClaudePlugins(Module):
    name = "claude-plugins"
    category = "cli"
    description = "Register Claude marketplaces + install enabled plugins; resolve CLICKUP token."
    # Secrets → ~/.git-credentials (private clickup-flow marketplace clone auth).
    # PassStore → the GPG password store (CLICKUP token).
    requires = (ClaudeCode, Dotfiles, Secrets, PassStore)
    profiles = ("claude",)

    def _settings_path(self) -> Path:
        return _home() / ".claude" / "settings.json"

    def _merge_settings(self, ctx: Ctx) -> None:
        path = self._settings_path()
        data: dict[str, object] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warn("claude-plugins: settings.json is not valid JSON — left untouched")
                return
            if isinstance(loaded, dict):
                data = loaded
        markets_raw = data.get("extraKnownMarketplaces")
        markets: dict[str, object] = markets_raw if isinstance(markets_raw, dict) else {}
        for name, src in MARKETPLACES.items():
            markets[name] = {"source": src}
        data["extraKnownMarketplaces"] = markets
        enabled_raw = data.get("enabledPlugins")
        enabled: dict[str, object] = enabled_raw if isinstance(enabled_raw, dict) else {}
        for plugin in ENABLED_PLUGINS:
            enabled[plugin] = True
        data["enabledPlugins"] = enabled
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def verify(self, ctx: Ctx) -> bool:
        path = self._settings_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        enabled = data.get("enabledPlugins")
        return isinstance(enabled, dict) and all(p in enabled for p in ENABLED_PLUGINS)

    def install(self, ctx: Ctx) -> None:
        self._merge_settings(ctx)
