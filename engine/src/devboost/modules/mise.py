"""mise — install the runtime version manager and migrate nvm/sdkman init blocks."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import config, mise
from devboost.exec.primitives.config import _atomic_write
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula
from devboost.modules.macos import Homebrew
from devboost.modules.shell import back_up_once

_NOTE_NVM = "# devboost: migrated nvm init to mise"
_NOTE_SDKMAN = "# devboost: migrated sdkman init to mise"

# mise is not in Ubuntu apt; its apt repo needs a dearmored key + per-arch suite. The
# official cross-distro installer (https://mise.run) avoids all of that and drops the
# binary in ~/.local/bin (on the executor's PATH), so verify (`which mise`) succeeds.
_MISE_INSTALL = "curl https://mise.run | sh"

#: rc files nvm/sdkman may have written `# BEGIN ...` / `# END ...` blocks into, per OS
#: family (Z2 ruling R2). macOS: M2 leaves ~/.zshrc.local, ~/.zprofile.local and
#: ~/.bash_profile.local to the user — ~/.zshrc / ~/.zprofile are chezmoi-managed, and
#: their drifted copies go to .pre-devboost. Every other family (Linux) keeps ~/.bashrc.
_RC_FILES: dict[str, tuple[str, ...]] = {
    "macos": (".zshrc.local", ".zprofile.local", ".bash_profile.local"),
}
_RC_FILES_DEFAULT: tuple[str, ...] = (".bashrc",)


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class Mise(Module):
    name = "mise"
    category = "base"
    description = "Install mise runtime version manager; migrate nvm/sdkman init blocks."
    profiles = ("base",)
    requires = (Homebrew,)  # macOS installs through brew (per_os); dropped on Linux
    # macOS: brew's formula, then the same nvm/sdkman migration below (rc files by OS).
    per_os = OsMap(macos=BrewFormula("mise"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("mise")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
        else:
            if ctx.os.family == "debian":
                self._cleanup_legacy_apt_source(ctx)
            if not ctx.ex.which("mise"):
                # Official cross-distro installer → ~/.local/bin (on PATH), no root. mise
                # is not in Fedora's default repos (`dnf install mise` fails), so use the
                # script on every OS.
                ctx.ex.run(["sh", "-c", _MISE_INSTALL])
        self._migrate_nvm(ctx)
        self._migrate_sdkman(ctx)

    def _cleanup_legacy_apt_source(self, ctx: Ctx) -> None:
        """Remove the malformed mise apt repo earlier versions (≤0.1.5) wrote.

        That broken source (wrong URL/suite + an un-dearmored key) makes every subsequent
        ``apt-get update`` fail with exit 100, which silently degrades unrelated installs.
        Removing it is idempotent and unblocks apt on already-affected boxes.
        """
        ctx.ex.run(
            ["rm", "-f",
             "/etc/apt/sources.list.d/mise-jdx-dev.list",
             "/etc/apt/keyrings/mise-jdx-dev.gpg"],
            sudo=True,
        )

    def _migrate_nvm(self, ctx: Ctx) -> None:
        nvm_dir = _home() / ".nvm"
        if not nvm_dir.is_dir():
            return
        self._comment_out(ctx, "# BEGIN NVM", "# END NVM", _NOTE_NVM)
        alias = nvm_dir / "alias" / "default"
        if alias.is_file():
            ver = alias.read_text(encoding="utf-8").strip().lstrip("v")
            if ver:
                mise.use_global(ctx, f"node@{ver}")

    def _migrate_sdkman(self, ctx: Ctx) -> None:
        sdkman_dir = _home() / ".sdkman"
        if not sdkman_dir.is_dir():
            return
        self._comment_out(ctx, "# BEGIN SDKMAN", "# END SDKMAN", _NOTE_SDKMAN)
        current = sdkman_dir / "candidates" / "java" / "current"
        if current.exists():
            ver = current.resolve().name
            if ver and ver != "current":
                mise.use_global(ctx, f"java@{ver}")

    def _rc_files(self, ctx: Ctx) -> tuple[Path, ...]:
        names = _RC_FILES.get(ctx.os.family, _RC_FILES_DEFAULT)
        return tuple(_home() / name for name in names)

    def _comment_out(self, ctx: Ctx, begin: str, end: str, note: str) -> None:
        for rc in self._rc_files(ctx):
            if not rc.exists():
                continue
            # errors="replace": a non-UTF-8 byte in this user-owned rc file must not
            # crash the migration (and block everything mise gates) — the file is only
            # ever read here to find the BEGIN/END markers, never re-encoded verbatim.
            text = rc.read_text(encoding="utf-8", errors="replace")
            if begin not in text or note in text:
                if note in text:
                    log.skip(f"mise: {begin} block already migrated in {rc.name}")
                continue
            # Back up once before the first rewrite — dev-boost never touched this file
            # before, and a crash mid-write must not be able to truncate the user's own rc.
            back_up_once(rc)
            _atomic_write(rc, config.comment_block(text, begin, end) + note + "\n")
