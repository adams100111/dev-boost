"""editors profile — Zed (default), the fresh terminal editor + base LSP set; VS Code (opt-in)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, DnfRepo, Module
from devboost.modules import _zed
from devboost.modules._lsp import LspModule, all_pins, seed_base_config
from devboost.modules.mise import Mise

_MS_KEY = "https://packages.microsoft.com/keys/microsoft.asc"
_VSCODE_SOURCE: pkg.Source = OsMap(
    fedora=DnfRepo(
        name="code",
        baseurl="https://packages.microsoft.com/yumrepos/vscode",
        gpgcheck=True,
        gpgkey=_MS_KEY,
    ),
    debian=AptRepo(
        list_line=(
            "deb [arch=amd64,arm64,armhf"
            " signed-by=/etc/apt/keyrings/packages-microsoft-com.gpg]"
            " https://packages.microsoft.com/repos/code stable main"
        ),
        key_url=_MS_KEY,
    ),
)
_FRESH_INSTALL = "https://raw.githubusercontent.com/sinelaw/fresh/refs/heads/master/scripts/install.sh"
_ZED_INSTALL = "https://zed.dev/install.sh"


def _home() -> Path:
    return Path(os.environ["HOME"])


def zed_install_argv(os_info: OsInfo) -> list[str]:
    """How Zed is installed on *os_info*.

    Linux (every family, Arch included): the official user-local script — ~/.local/zed.app
    plus a ~/.local/bin/zed symlink, no sudo. Distro packages are avoided on purpose: Arch
    ships the CLI as `zeditor`, which would break `VISUAL="zed --wait"`. Zed updates itself.
    """
    if os_info.family == "macos":
        raise UnsupportedOS("zed: macOS installs via the Homebrew cask (Zed milestone Z2)")
    return ["sh", "-c", f"curl -fsSL {_ZED_INSTALL} | sh"]


@register
class Vscode(Module):
    name = "vscode"
    category = "optional-editors"
    description = "Visual Studio Code (Microsoft repo) — opt-in; Zed is the default editor."
    gui = True
    profiles = ("optional-editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("code")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "arch":
            # Arch's own `code` package is the OSS rebuild (no Marketplace, no MS
            # branding). The Microsoft build is `visual-studio-code-bin`, which Omarchy
            # also mirrors in its own repo — the AUR helper resolves either source.
            pkg.install_aur(ctx, "visual-studio-code-bin")
            return
        if ctx.os.family == "fedora":
            # Fedora: import the GPG key into the RPM keyring before adding the repo
            ctx.ex.run(["rpm", "--import", _MS_KEY], sudo=True)
        pkg.install(ctx, "code", source=_VSCODE_SOURCE)


@register
class Zed(Module):
    name = "zed"
    category = "editors"
    description = "Zed — default GUI editor; curated settings, in-editor agents, pinned LSPs."
    gui = True
    profiles = ("editors",)
    #: Linux only until milestone Z2 adds "macos" (+ the cask branch in zed_install_argv).
    families = ("fedora", "debian", "arch")

    @staticmethod
    def _installed(ctx: Ctx) -> bool:
        # The script's symlink is checked directly: ~/.local/bin may not be on PATH yet in
        # the install session (same reason DotnetLsp checks ~/.dotnet/tools).
        return (_home() / ".local" / "bin" / "zed").exists() or ctx.ex.which("zed")

    def verify(self, ctx: Ctx) -> bool:
        return self._installed(ctx) and _zed.config_ok(all_pins())

    def install(self, ctx: Ctx) -> None:
        if not self._installed(ctx):
            argv = zed_install_argv(ctx.os)
            res = ctx.ex.run(argv)
            if not res.ok:
                raise InstallError(self.name, argv[-1], res.code)
        _zed.ensure_config(ctx, all_pins())


@register
class Fresh(Module):
    name = "fresh"
    category = "editors"
    description = "The fresh terminal editor."
    profiles = ("editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("fresh")

    def install(self, ctx: Ctx) -> None:
        # Upstream installer (rpm asset + post-install script); curl|sh escape hatch.
        ctx.ex.run(["sh", "-c", f"curl -fsSL {_FRESH_INSTALL} | sh"])
        # Seed the base config so the editor is configured even in a bare `terminal`
        # install (no LSP module present to seed it). Idempotent: only writes if absent.
        seed_base_config()


@register
class FreshLsp(LspModule):
    name = "fresh-lsp"
    description = "Provision fresh's base LSP servers (mise-pinned) + config."
    requires = (Fresh, Mise)
    profiles = ("editors",)
    servers_file = "servers.base.tsv"
