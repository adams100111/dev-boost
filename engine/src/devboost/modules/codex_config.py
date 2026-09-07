"""codex-config — merge shareable ~/.codex/config.toml sections (prefs, features, shell env)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.codex_code import CodexCode
from devboost.modules.optional import PassStore
from devboost.modules.shell import Dotfiles

CODEX_PREFS: dict[str, str] = {
    "model": "gpt-5.6-sol",
    "model_reasoning_effort": "low",
}


def _home() -> Path:
    return Path(os.environ["HOME"])


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@register
class CodexConfig(Module):
    name = "codex-config"
    category = "cli"
    description = (
        "Merge shareable ~/.codex/config.toml prefs/features/shell-env (CLICKUP via pass)."
    )
    requires = (CodexCode, Dotfiles, PassStore)
    profiles = ("codex",)

    def _config_path(self) -> Path:
        return _home() / ".codex" / "config.toml"

    def _clickup(self, ctx: Ctx) -> str | None:
        if not ctx.ex.which("pass"):
            log.warn("codex-config: pass not configured — skipping CLICKUP_API_TOKEN")
            return None
        res = ctx.ex.run(["pass", "show", "clickup/api-token"])
        token = res.stdout.strip()
        if not res.ok or not token:
            log.warn("codex-config: `pass show clickup/api-token` missing — skipping token")
            return None
        return token

    def verify(self, ctx: Ctx) -> bool:
        path = self._config_path()
        if not path.exists():
            return False
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return False
        return data.get("model") == CODEX_PREFS["model"] and bool(
            data.get("features", {}).get("hooks")
        )

    def install(self, ctx: Ctx) -> None:
        path = self._config_path()
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError:
                log.warn("codex-config: config.toml is not valid TOML — left untouched")
                return
        managed: dict[str, Any] = dict(CODEX_PREFS)
        managed["features"] = {"hooks": True}
        managed["shell_environment_policy"] = {"inherit": "core"}
        token = self._clickup(ctx)
        if token is not None:
            managed["shell_environment_policy"]["set"] = {"CLICKUP_API_TOKEN": token}
        _deep_merge(data, managed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(data) + "", encoding="utf-8")
