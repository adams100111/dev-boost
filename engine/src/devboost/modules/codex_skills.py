"""codex-skills — ensure ~/.agents/skills (Codex's shared user-skills dir) is populated."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_skills import _lock_entries, hydrate_skills, skill_present
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
    portable: ClassVar[bool] = True  # `npx skills add`

    def _present(self, name: str) -> bool:
        # Codex reads USER skills from ~/.agents/skills (auto-discovered) — the same real-content
        # dir ~/.claude/skills symlinks into. NOT ~/.codex/skills; no -a codex / [[skills.config]].
        return skill_present(_home() / ".agents" / "skills", name)

    def verify(self, ctx: Ctx) -> bool:
        return all(self._present(name) for _, name in _lock_entries(_home()))

    def install(self, ctx: Ctx) -> None:
        hydrate_skills(ctx, self.name, _home() / ".agents" / "skills")
