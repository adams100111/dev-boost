"""worktrunk — `wt`, git worktrees for parallel agents (pinned, SHA256-verified binary),
plus its Claude Code and Codex plugins so every harness creates worktrees through `wt`."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.media.catalog import asset_key, worktrunk_pin
from devboost.model import Ctx, Module
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.claude_plugins import claude_plugin_names
from devboost.modules.codex_code import CodexCode


def _version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


@register
class Worktrunk(Module):
    name = "worktrunk"
    category = "cli"
    description = "worktrunk (wt) — git worktrees for parallel agents (pinned binary)."
    profiles = ("cli", "brain-tools")
    #: Same install code on every OS: the catalog pin is keyed by (os, arch).
    portable: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("wt"):
            return False
        res = ctx.ex.run(["wt", "--version"])
        have = _version(res.stdout)
        if not res.ok or have is None:
            # A corrupt or wrong-arch binary must not pass as installed: reinstall it.
            return False
        # An older pin is upgraded; a newer wt (installed by hand) is kept as is.
        want = _version(worktrunk_pin().version)
        return want is None or have >= want

    def install(self, ctx: Ctx) -> None:
        pin = worktrunk_pin()
        key = asset_key(ctx.os)
        asset = pin.assets.get(key)
        if asset is None:
            raise InstallError("worktrunk", f"no pinned binary for {key!r}", 1)
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        check = "shasum -a 256 -c -" if ctx.os.family == "macos" else "sha256sum -c -"
        # Download → verify SHA256 (fails `set -e` before anything is installed) → unpack
        # → put `wt` and `git-wt` on PATH. Shell integration is NOT written here: the rc
        # files belong to chezmoi, so devboost's shell.zsh / shell.bash run
        # `wt config shell init` themselves.
        script = (
            "set -e\n"
            "tmp=$(mktemp -d)\n"
            "trap 'rm -rf \"$tmp\"' EXIT\n"
            f'curl -fL --proto \'=https\' --retry 2 -o "$tmp/wt.tar.xz" "{asset.url}"\n'
            f'echo "{asset.sha256}  $tmp/wt.tar.xz" | {check}\n'
            'tar -xJf "$tmp/wt.tar.xz" -C "$tmp"\n'
            f'mkdir -p "{bindir}"\n'
            f'for b in wt git-wt; do install -m 755 "$tmp"/worktrunk-*/"$b" "{bindir}/$b"; done\n'
        )
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise InstallError("worktrunk", "download or checksum verification failed", res.code)


#: What `wt config plugins <harness> install` adds (worktrunk v0.83.0 docs, claude-code.md).
CLAUDE_PLUGINS: tuple[str, ...] = ("worktrunk",)
CODEX_PLUGINS: tuple[str, ...] = ("worktrunk", "worktrunk-markers")


@register
class WorktrunkAgents(Module):
    """worktrunk's own agent plugins, installed through `wt` so its version owns the layout.

    Claude Code: the skill, activity markers in `wt list`, and the WorktreeCreate /
    WorktreeRemove hooks that route agent worktrees (`isolation: "worktree"`) through
    `wt switch --create` / `wt remove` — this is what makes `wt` the default there.
    Codex: the skill plus activity markers (Codex has no worktree hook to take over).
    A harness that is not installed is skipped; the other still gets its plugins.
    """

    name = "worktrunk-agents"
    category = "cli"
    description = "worktrunk plugins for Claude Code and Codex (wt-managed agent worktrees)."
    requires = (Worktrunk,)
    # Soft: plugins go into whichever harness this plan installs (or the box already has).
    after = (ClaudeCode, CodexCode)
    profiles = ("cli", "brain-tools")
    portable: ClassVar[bool] = True  # only drives the wt, claude and codex CLIs

    def _claude_installed(self, ctx: Ctx) -> set[str]:
        res = ctx.ex.run(["claude", "plugin", "list", "--json"])
        try:
            entries = json.loads(res.stdout) if res.ok else []
        except ValueError:
            entries = []
        return claude_plugin_names(entries)

    def _codex_installed(self, ctx: Ctx) -> set[str]:
        # codex wraps entries in {"installed": [...], ...} (see codex_plugins).
        res = ctx.ex.run(["codex", "plugin", "list", "--json"])
        try:
            data: object = json.loads(res.stdout) if res.ok else None
        except ValueError:
            data = None
        entries = data.get("installed") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return set()
        return {
            e["name"]
            for e in entries
            if isinstance(e, dict) and e.get("installed") and isinstance(e.get("name"), str)
        }

    def _missing(self, ctx: Ctx) -> list[str]:
        """Harnesses on this box whose worktrunk plugins are not all installed."""
        todo: list[str] = []
        if ctx.ex.which("claude") and not set(CLAUDE_PLUGINS) <= self._claude_installed(ctx):
            todo.append("claude")
        if ctx.ex.which("codex") and not set(CODEX_PLUGINS) <= self._codex_installed(ctx):
            todo.append("codex")
        return todo

    def verify(self, ctx: Ctx) -> bool:
        return not self._missing(ctx)

    def install(self, ctx: Ctx) -> None:
        if not (ctx.ex.which("claude") or ctx.ex.which("codex")):
            log.warn("worktrunk-agents: neither claude nor codex found — skipping")
            return
        for harness in self._missing(ctx):
            res = ctx.ex.run(["wt", "config", "plugins", harness, "install", "--yes"])
            if not res.ok:
                log.warn(f"worktrunk-agents: {harness} plugins failed: {res.stderr.strip()}")
