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

    def _install_plugins(self, ctx: Ctx) -> None:
        if not ctx.ex.which("claude"):
            log.warn("claude-plugins: claude CLI not found — skipping plugin install")
            return
        # `list` plain-text format is unstable; `--json` gives {name, marketplace, …} per entry.
        listed = ctx.ex.run(["claude", "plugin", "list", "--json"])
        installed: set[str] = set()
        if listed.ok:
            try:
                entries = json.loads(listed.stdout)
            except ValueError:
                entries = []
            if isinstance(entries, list):
                installed = {
                    e["name"]
                    for e in entries
                    if isinstance(e, dict) and isinstance(e.get("name"), str)
                }
        for plugin in ENABLED_PLUGINS:
            name = plugin.split("@", 1)[0]
            if name in installed:
                log.skip(f"claude-plugins: {plugin} already installed")
                continue
            # --yes: non-interactive (auto-approves any headersHelper/command prompts).
            res = ctx.ex.run(["claude", "plugin", "install", plugin, "--scope", "user", "--yes"])
            if not res.ok:
                log.warn(f"claude-plugins: install {plugin} failed: {res.stderr.strip()}")

    def _resolve_clickup_token(self, ctx: Ctx) -> None:
        if not ctx.ex.which("pass"):
            log.warn("claude-plugins: pass not configured — skipping CLICKUP_API_TOKEN")
            return
        res = ctx.ex.run(["pass", "show", "clickup/api-token"])
        token = res.stdout.strip()
        if not res.ok or not token:
            log.warn("claude-plugins: `pass show clickup/api-token` missing — skipping token")
            return
        local = _home() / ".claude" / "settings.local.json"
        data: dict[str, object] = {}
        if local.exists():
            try:
                loaded = json.loads(local.read_text(encoding="utf-8"))
            except ValueError:
                log.warn("claude-plugins: settings.local.json invalid JSON — left untouched")
                return
            if isinstance(loaded, dict):
                data = loaded
        env_raw = data.get("env")
        env: dict[str, object] = env_raw if isinstance(env_raw, dict) else {}
        env["CLICKUP_API_TOKEN"] = token
        data["env"] = env
        local.parent.mkdir(parents=True, exist_ok=True)
        data_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        fd = os.open(local, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data_bytes)
        finally:
            os.close(fd)
        os.chmod(local, 0o600)  # also tighten a pre-existing file (O_TRUNC keeps old mode)

    def install(self, ctx: Ctx) -> None:
        self._merge_settings(ctx)
        self._install_plugins(ctx)
        self._resolve_clickup_token(ctx)
