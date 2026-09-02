"""Omarchy integration — hand the dev layer to Omarchy's own update run.

Omarchy owns system packages, AUR packages and mise runtimes: `omarchy update` takes a
snapshot, syncs pacman, runs migrations, then updates AUR and mise. Building a second
update path alongside it would be the worst outcome of supporting this platform — two
tools racing over pacman, with dev-boost skipping the pre-update snapshot.

So dev-boost does not duplicate any of that. It registers a `post-update` hook, which
`omarchy update` runs after packages and migrations, and refreshes only the layer Omarchy
does not manage: the pinned CLI tools dev-boost installs itself. One `omarchy update` then
brings the OS *and* the dev stack current, with a rollback snapshot already taken.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.model import Ctx, Module

_HOOK_NAME = "devboost-update"
_HOOK_TYPE = "post-update"

#: The hook body. Exits 0 even when the refresh fails: at that point the OS update itself
#: has already succeeded, and the dev-layer refresh is separable and safely re-runnable —
#: failing here would brand a good system update as broken over a transient network error.
_HOOK_BODY = """\
#!/bin/bash
# devboost — refresh the dev layer after `omarchy update`.
# Managed by dev-boost (module: omarchy-update-hook). Do not edit; re-run
# `devboost install omarchy-update-hook --force` to restore.

command -v devboost >/dev/null 2>&1 || exit 0

echo "devboost: refreshing dev tooling…"
if devboost install --update; then
  echo "devboost: dev tooling up to date."
else
  echo "devboost: refresh failed — the system update itself was fine." >&2
  echo "devboost: re-run \\`devboost install --update\\` when convenient." >&2
fi
exit 0
"""


def _hooks_dir() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "omarchy" / "hooks" / f"{_HOOK_TYPE}.d"


def _hook_path() -> Path:
    return _hooks_dir() / _HOOK_NAME


@register
class OmarchyUpdateHook(Module):
    name = "omarchy-update-hook"
    category = "omarchy"
    description = "Refresh dev-boost's tooling as part of `omarchy update` (post-update hook)."
    profiles = ("omarchy",)
    # Arch-family only. On vanilla Arch there is no `omarchy` command, and install()
    # degrades to a clean no-op rather than failing the run.
    families: ClassVar[tuple[str, ...]] = ("arch",)

    def _omarchy_present(self, ctx: Ctx) -> bool:
        return ctx.ex.which("omarchy-hook-install")

    def verify(self, ctx: Ctx) -> bool:
        if not self._omarchy_present(ctx):
            return True  # nothing to integrate with — not a failure
        path = _hook_path()
        return path.is_file() and "devboost install --update" in path.read_text(
            encoding="utf-8"
        )

    def install(self, ctx: Ctx) -> None:
        if not self._omarchy_present(ctx):
            log.warn("omarchy-update-hook: no omarchy CLI found — skipping hook install")
            return
        # Write to the hook directory directly. `omarchy hook install` copies a file into
        # this same path; writing it ourselves is the identical result without needing a
        # staging file, and it stays idempotent on re-run.
        target = _hook_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(_HOOK_BODY, encoding="utf-8")
            target.chmod(0o755)
        except OSError as exc:
            raise InstallError("omarchy-update-hook", f"write {target}", 1) from exc
        log.ok(f"omarchy-update-hook: installed {target}")
