"""optional-editors + security-cli profiles (opt-in, off the production path)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import ConfigError
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules.secrets import Secrets


@register
class Neovim(Module):
    name = "neovim"
    category = "optional-editors"
    description = "Neovim editor."
    profiles = ("optional-editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("nvim")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "neovim")


@register
class JetbrainsToolbox(Module):
    name = "jetbrains-toolbox"
    category = "optional-editors"
    description = "JetBrains Toolbox app."
    gui = True
    profiles = ("optional-editors",)

    def _bin(self) -> Path:
        return Path(os.environ["HOME"]) / ".local" / "bin" / "jetbrains-toolbox"

    def verify(self, ctx: Ctx) -> bool:
        return self._bin().exists()

    def install(self, ctx: Ctx) -> None:
        self._bin().parent.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(
            ["sh", "-c",
             "curl -fsSL 'https://data.services.jetbrains.com/products/download"
             "?code=TBA&platform=linux' -o /tmp/jbtb.tar.gz && "
             f"tar -xzf /tmp/jbtb.tar.gz -C {self._bin().parent} --strip-components=1"]
        )


@register
class Pass(Module):
    name = "pass"
    category = "security-cli"
    description = "pass password-store CLI."
    profiles = ("security-cli",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("pass")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "pass")


@register
class PassStore(Module):
    name = "pass-store"
    category = "security-cli"
    description = "Initialize the GPG-backed password store (optionally cloned)."
    requires = (Pass, Secrets)
    profiles = ("security-cli",)

    def _store(self) -> Path:
        override = os.environ.get("PASSWORD_STORE_DIR")
        return Path(override) if override else Path(os.environ["HOME"]) / ".password-store"

    def verify(self, ctx: Ctx) -> bool:
        return self._store().is_dir()

    def install(self, ctx: Ctx) -> None:
        repo = os.environ.get("DEVBOOST_PASS_REPO")
        if repo:
            res = ctx.ex.run(["git", "clone", repo, str(self._store())])
            if not res.ok:
                raise ConfigError(
                    f"pass-store: cloning DEVBOOST_PASS_REPO ({repo}) failed (exit {res.code}) — "
                    "check the repo URL and your git credentials"
                )
            return
        gpg_id = os.environ.get("DEVBOOST_PASS_GPG_ID")
        if not gpg_id:
            raise ConfigError(
                "pass-store: no pass store configured — set DEVBOOST_PASS_REPO to clone your "
                "existing pass repo, or DEVBOOST_PASS_GPG_ID to initialize a new store"
            )
        res = ctx.ex.run(["pass", "init", gpg_id])
        if not res.ok:
            raise ConfigError(f"pass-store: `pass init {gpg_id}` failed (exit {res.code})")
