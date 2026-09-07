"""claude-skills — reproduce lockfile-tracked skills via `npx skills add`."""

from __future__ import annotations

import json
import os
from pathlib import Path

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.shell import Dotfiles


def _home() -> Path:
    return Path(os.environ["HOME"])


def _lock_entries(home: Path) -> list[tuple[str, str]]:
    """Return (source, skill_name) pairs from ~/.agents/.skill-lock.json (empty if absent)."""
    lock = home / ".agents" / ".skill-lock.json"
    if not lock.is_file():
        return []
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, dict):
        return []
    out: list[tuple[str, str]] = []
    for name, meta in skills.items():
        source = meta.get("source") if isinstance(meta, dict) else None
        if isinstance(source, str) and source:
            out.append((source, name))
    return out


@register
class ClaudeSkills(Module):
    name = "claude-skills"
    category = "cli"
    description = "Reproduce lockfile-tracked skills via `npx skills add`."
    requires = (ClaudeCode, Dotfiles)
    profiles = ("claude",)

    def _present(self, name: str) -> bool:
        p = _home() / ".claude" / "skills" / name
        return p.exists() or p.is_symlink()

    def verify(self, ctx: Ctx) -> bool:
        entries = _lock_entries(_home())
        return all(self._present(name) for _, name in entries)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("npx"):
            log.warn("claude-skills: npx not found — skipping skill hydration")
            return
        for source, name in _lock_entries(_home()):
            if self._present(name):
                log.skip(f"claude-skills: {name} already present")
                continue
            res = ctx.ex.run(["npx", "skills", "add", f"{source}@{name}", "-g", "-y"])
            if not res.ok:
                log.warn(
                    f"claude-skills: `skills add {source}@{name}` failed — vendor it instead"
                )
