"""claude-skills — reproduce lockfile-tracked skills (vendored copy first, else `npx skills add`).

A skill the upstream repo no longer serves (renamed or deleted) is vendored in the bundled
dotfiles source instead: the real content under ``private_dot_agents/skills/<dir>`` and a
``symlink_<dir>`` under ``private_dot_claude/skills``, as the CLI itself lays it out. The
dotfiles module normally puts those in place first; this module restores a missing one from
there, and reports a skill it can neither restore nor fetch as ``NeedsUser`` (blocked) with
the fix, so a dead upstream never fails the run on every rerun.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.core.registry import register
from devboost.core.settings import settings
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


def install_dir_name(name: str) -> str:
    """The directory `npx skills add` installs a skill into, from its lock-file name.

    The lock file keys skills by their SKILL.md ``name``, which may be a display name
    ("Poteto Mode"); the CLI installs into ``sanitizeName(name)`` ("poteto-mode"). Mirrors
    vercel-labs/skills ``sanitizeName``: lowercase, runs of other characters become "-",
    leading/trailing dots and hyphens trimmed, at most 255 characters.
    """
    out = re.sub(r"[^a-z0-9._]+", "-", name.lower())
    out = re.sub(r"^[.\-]+|[.\-]+$", "", out)[:255]
    return out or "unnamed-skill"


def skill_present(skills_dir: Path, name: str) -> bool:
    """True when the lock-file skill *name* is installed under *skills_dir*."""
    for dirname in dict.fromkeys((name, install_dir_name(name))):
        p = skills_dir / dirname
        if p.exists() or p.is_symlink():
            return True
    return False


#: (home skills dir, where the bundled dotfiles source vendors skills for it). The agents
#: dir comes first: a Claude-side ``symlink_<dir>`` points into it.
_VENDOR_DIRS: tuple[tuple[str, str], ...] = (
    (".agents/skills", "private_dot_agents/skills"),
    (".claude/skills", "private_dot_claude/skills"),
)
#: The lock file's place in the dotfiles source, named in the fix for an unfetchable skill.
_LOCK_SOURCE = "dotfiles/private_dot_agents/dot_skill-lock.json"


def vendored_targets(home: Path, name: str) -> list[Path]:
    """The home paths the bundled dotfiles source vendors for skill *name* (empty: none)."""
    src = settings.root / "dotfiles"
    out: list[Path] = []
    for home_rel, src_rel in _VENDOR_DIRS:
        base = src / src_rel
        for dirname in dict.fromkeys((name, install_dir_name(name))):
            if (base / dirname).is_dir() or (base / f"symlink_{dirname}").is_file():
                out.append(home / home_rel / dirname)
                break
    return out


def _restore_vendored(ctx: Ctx, home: Path, targets: list[Path]) -> bool:
    """Apply just *targets* from the bundled dotfiles source (the dotfiles module's own
    mechanism). chezmoi does not create a target's parents, so they are made first."""
    if not ctx.ex.which("chezmoi"):
        return False
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
    src = settings.root / "dotfiles"
    argv = ["chezmoi", "apply", "--force", "--source", str(src), "--destination", str(home)]
    return ctx.ex.run([*argv, *(str(t) for t in targets)]).ok


def hydrate_skills(ctx: Ctx, label: str, skills_dir: Path) -> None:
    """Make every lock-file skill present under *skills_dir*.

    Per missing skill: restore the vendored copy when the dotfiles source has one (never
    fetched: the vendored copy is what the user runs), else `npx skills add`. A skill that
    is still missing afterwards raises one ``NeedsUser`` naming each skill and its fix.
    """
    home = _home()
    have_npx = ctx.ex.which("npx")
    unfetchable: list[str] = []  # upstream no longer serves it (or the CLI failed)
    unrestored: list[str] = []  # vendored, but the copy did not apply
    no_npx: list[str] = []
    for source, name in _lock_entries(home):
        if skill_present(skills_dir, name):
            log.skip(f"{label}: {name} already present")
            continue
        targets = vendored_targets(home, name)
        if targets:
            if _restore_vendored(ctx, home, targets) and skill_present(skills_dir, name):
                log.ok(f"{label}: {name} restored from its vendored copy")
            else:
                unrestored.append(name)
            continue
        if not have_npx:
            no_npx.append(name)
            continue
        res = ctx.ex.run(["npx", "skills", "add", f"{source}@{name}", "-g", "-y"])
        if not (res.ok and skill_present(skills_dir, name)):
            log.warn(f"{label}: `skills add {source}@{name}` failed — {source} may no "
                     "longer provide it")
            unfetchable.append(f"{name} ({source})")
    problems: list[tuple[str, str]] = []
    if unfetchable:
        problems.append((
            f"can't fetch {', '.join(unfetchable)}",
            f"vendor each installed copy into dotfiles/private_dot_agents/skills/ or remove "
            f"it from {_LOCK_SOURCE}",
        ))
    if unrestored:
        problems.append((
            f"vendored {', '.join(unrestored)} did not apply",
            f"run `chezmoi apply --force --source {settings.root / 'dotfiles'}` (needs "
            "chezmoi) and check the vendored copy under dotfiles/private_dot_agents/skills/",
        ))
    if no_npx:
        problems.append((
            f"npx not found for {', '.join(no_npx)}",
            "install Node.js so `npx` is on PATH, then re-run",
        ))
    if problems:
        raise NeedsUser(
            f"{label}: " + "; ".join(r for r, _ in problems),
            "; ".join(f for _, f in problems),
        )


@register
class ClaudeSkills(Module):
    name = "claude-skills"
    category = "cli"
    description = "Reproduce lockfile-tracked skills (vendored copy, else `npx skills add`)."
    requires = (ClaudeCode, Dotfiles)
    profiles = ("claude",)
    portable: ClassVar[bool] = True  # `npx skills add`

    def _present(self, name: str) -> bool:
        return skill_present(_home() / ".claude" / "skills", name)

    def verify(self, ctx: Ctx) -> bool:
        entries = _lock_entries(_home())
        return all(self._present(name) for _, name in entries)

    def install(self, ctx: Ctx) -> None:
        hydrate_skills(ctx, self.name, _home() / ".claude" / "skills")
