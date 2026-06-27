"""editors profile — VS Code, the fresh terminal editor, and its base LSP set."""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, DnfRepo, Module
from devboost.modules._lsp import LspModule
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


@register
class Vscode(Module):
    name = "vscode"
    category = "editors"
    description = "Visual Studio Code (Microsoft repo)."
    gui = True
    profiles = ("editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("code")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            # Fedora: import the GPG key into the RPM keyring before adding the repo
            ctx.ex.run(["rpm", "--import", _MS_KEY], sudo=True)
        pkg.install(ctx, "code", source=_VSCODE_SOURCE)


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


@register
class FreshLsp(LspModule):
    name = "fresh-lsp"
    description = "Provision fresh's base LSP servers (mise-pinned) + config."
    requires = (Fresh, Mise)
    profiles = ("editors",)
    servers_file = "servers.base.tsv"
