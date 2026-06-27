"""mise — install the runtime version manager and migrate nvm/sdkman init blocks."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import config, mise, pkg
from devboost.model import AptRepo, Ctx, Module

_NOTE_NVM = "# devboost: migrated nvm init to mise"
_NOTE_SDKMAN = "# devboost: migrated sdkman init to mise"

_MISE_APT_SOURCE: pkg.Source = OsMap(
    debian=AptRepo(
        list_line=(
            "deb [signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg]"
            " https://mise.jdx.dev/apt/ * *"
        ),
        key_url="https://mise.jdx.dev/gpg-key.pub",
    )
)


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class Mise(Module):
    name = "mise"
    category = "base"
    description = "Install mise runtime version manager; migrate nvm/sdkman init blocks."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("mise")

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("mise"):
            if ctx.os.family == "debian":
                pkg.install(ctx, "mise", source=_MISE_APT_SOURCE)
            else:
                pkg.install(ctx, "mise")
        self._migrate_nvm(ctx)
        self._migrate_sdkman(ctx)

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

    def _comment_out(self, ctx: Ctx, begin: str, end: str, note: str) -> None:
        bashrc = _home() / ".bashrc"
        if not bashrc.exists():
            return
        text = bashrc.read_text(encoding="utf-8")
        if begin not in text or note in text:
            if note in text:
                log.skip(f"mise: {begin} block already migrated")
            return
        bashrc.write_text(config.comment_block(text, begin, end) + note + "\n", encoding="utf-8")
