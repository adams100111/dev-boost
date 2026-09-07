"""codex-skills — ensure ~/.agents/skills (Codex's shared user-skills dir) is populated."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_skills import _lock_entries
from devboost.modules.codex_code import CodexCode
from devboost.modules.shell import Dotfiles


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class CodexSkills(Module):
    name = "codex-skills"
    category = "cli"
    description = "Ensure ~/.agents/skills (Codex USER skills, shared with ~/.claude) is populated."
    requires = (CodexCode, Dotfiles)
    profiles = ("codex",)

    def _present(self, name: str) -> bool:
        # Codex reads USER skills from ~/.agents/skills (auto-discovered) — the same real-content
        # dir ~/.claude/skills symlinks into. NOT ~/.codex/skills; no -a codex / [[skills.config]].
        p = _home() / ".agents" / "skills" / name
        return p.exists() or p.is_symlink()

    def verify(self, ctx: Ctx) -> bool:
        return all(self._present(name) for _, name in _lock_entries(_home()))

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("npx"):
            log.warn("codex-skills: npx not found — skipping skill hydration")
            return
        for source, name in _lock_entries(_home()):
            if self._present(name):
                log.skip(f"codex-skills: {name} already present")
                continue
            res = ctx.ex.run(["npx", "skills", "add", f"{source}@{name}", "-g", "-y"])
            if not res.ok:
                log.warn(f"codex-skills: `skills add {source}@{name}` failed — vendor it instead")
