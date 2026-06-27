"""shell profile — starship, ghostty, nerd-fonts, dotfiles, bash-config."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from devboost.core import log
from devboost.core.registry import register
from devboost.core.settings import settings
from devboost.exec.primitives import copr, flatpak, pkg
from devboost.model import Ctx, Module
from devboost.modules.base import Chezmoi
from devboost.modules.cli_tools import Atuin, Direnv, Zoxide

_NF_VERSION = "v3.2.1"
_NF_URL = (
    f"https://github.com/ryanoasis/nerd-fonts/releases/download/{_NF_VERSION}/JetBrainsMono.zip"
)


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class Starship(Module):
    name = "starship"
    category = "shell"
    description = "Cross-shell prompt."
    profiles = ("shell",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("starship")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "starship")


@register
class Ghostty(Module):
    name = "ghostty"
    category = "shell"
    description = "GPU-accelerated terminal (Fedora COPR / Flathub flatpak on Ubuntu)."
    gui = True
    profiles = ("shell",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "debian":
            return "com.mitchellh.ghostty" in ctx.ex.run(
                ["flatpak", "list", "--app", "--columns=application"]
            ).stdout
        return ctx.ex.which("ghostty")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            flatpak.install(ctx, "com.mitchellh.ghostty")
        else:
            copr.enable(ctx, "scottames/ghostty")
            pkg.install(ctx, "ghostty")


@register
class NerdFonts(Module):
    name = "nerd-fonts"
    category = "shell"
    description = "JetBrainsMono Nerd Font."
    profiles = ("shell",)

    def verify(self, ctx: Ctx) -> bool:
        return "JetBrainsMono Nerd Font" in ctx.ex.run(["fc-list"]).stdout

    def install(self, ctx: Ctx) -> None:
        font_dir = _home() / ".local" / "share" / "fonts" / "JetBrainsMono"
        font_dir.mkdir(parents=True, exist_ok=True)
        zip_path = Path(tempfile.gettempdir()) / "devboost-jetbrainsmono.zip"
        ctx.ex.run(["curl", "-fsSL", _NF_URL, "-o", str(zip_path)])
        ctx.ex.run(["unzip", "-o", str(zip_path), "-d", str(font_dir)])
        ctx.ex.run(["fc-cache", "-f"])


@register
class Dotfiles(Module):
    name = "dotfiles"
    category = "shell"
    description = "Apply the in-repo chezmoi dotfiles source."
    requires = (Chezmoi, Starship, Atuin, Zoxide, Direnv)
    profiles = ("shell",)

    def verify(self, ctx: Ctx) -> bool:
        bashrc = _home() / ".bashrc"
        return (_home() / ".config" / "starship.toml").exists() and bashrc.exists() and (
            "devboost" in bashrc.read_text(encoding="utf-8")
        )

    def install(self, ctx: Ctx) -> None:
        src = settings.root / "dotfiles"
        if not src.is_dir():
            log.warn(f"dotfiles: source not found ({src}) — skipping")
            return
        ctx.ex.run(
            ["chezmoi", "apply", "--source", str(src), "--destination", str(_home())]
        )


@register
class BashConfig(Module):
    name = "bash-config"
    category = "shell"
    description = "Verify the dotfiles-applied bash init (starship + devboost markers)."
    requires = (Dotfiles,)
    profiles = ("shell",)

    def verify(self, ctx: Ctx) -> bool:
        bashrc = _home() / ".bashrc"
        if not bashrc.exists():
            return False
        text = bashrc.read_text(encoding="utf-8")
        return "starship init bash" in text and "devboost" in text

    def install(self, ctx: Ctx) -> None:
        # No-op: the bashrc content is applied by the dotfiles module (this is a marker check).
        return
