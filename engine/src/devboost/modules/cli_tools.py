"""The base + cli package tools — one typed declaration each (shared PackageModule).

Each tool sets: name, category, profiles, cmd (verify), fedora_pkg (install), [copr_repo].
"""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule


@register
class Coreutils(PackageModule):
    name = "coreutils"
    category = "base"
    profiles = ("base",)
    cmd = "ls"
    fedora_pkg = "coreutils"


@register
class Git(PackageModule):
    name = "git"
    category = "base"
    profiles = ("base",)
    cmd = "git"
    fedora_pkg = "git"


@register
class Curl(PackageModule):
    name = "curl"
    category = "base"
    profiles = ("base",)
    cmd = "curl"
    fedora_pkg = "curl"


@register
class Wget(PackageModule):
    name = "wget"
    category = "base"
    profiles = ("base",)
    cmd = "wget"
    fedora_pkg = "wget"


@register
class Unzip(PackageModule):
    name = "unzip"
    category = "base"
    profiles = ("base",)
    cmd = "unzip"
    fedora_pkg = "unzip"


@register
class Jq(PackageModule):
    name = "jq"
    category = "base"
    profiles = ("base",)
    cmd = "jq"
    fedora_pkg = "jq"


@register
class Htop(PackageModule):
    name = "htop"
    category = "base"
    profiles = ("base",)
    cmd = "htop"
    fedora_pkg = "htop"


@register
class Fd(PackageModule):
    name = "fd"
    category = "base"
    profiles = ("base",)
    cmd = "fd"
    fedora_pkg = "fd-find"
    debian_cmd = "fdfind"   # Ubuntu binary is fdfind; apt package fd-find is same


@register
class Fzf(PackageModule):
    name = "fzf"
    category = "base"
    profiles = ("base",)
    cmd = "fzf"
    fedora_pkg = "fzf"


@register
class Tmux(PackageModule):
    name = "tmux"
    category = "base"
    profiles = ("base",)
    cmd = "tmux"
    fedora_pkg = "tmux"


@register
class Eza(PackageModule):
    name = "eza"
    category = "cli"
    profiles = ("cli",)
    cmd = "eza"
    fedora_pkg = "eza"


@register
class Bat(PackageModule):
    name = "bat"
    category = "cli"
    profiles = ("cli",)
    cmd = "bat"
    fedora_pkg = "bat"
    debian_cmd = "batcat"   # Ubuntu binary is batcat; apt package bat is same


@register
class Btop(PackageModule):
    name = "btop"
    category = "cli"
    profiles = ("cli",)
    cmd = "btop"
    fedora_pkg = "btop"


@register
class Zoxide(PackageModule):
    name = "zoxide"
    category = "cli"
    profiles = ("cli",)
    cmd = "zoxide"
    fedora_pkg = "zoxide"


@register
class Atuin(PackageModule):
    name = "atuin"
    category = "cli"
    profiles = ("cli",)
    cmd = "atuin"
    fedora_pkg = "atuin"


@register
class Direnv(PackageModule):
    name = "direnv"
    category = "cli"
    profiles = ("cli",)
    cmd = "direnv"
    fedora_pkg = "direnv"


@register
class Delta(PackageModule):
    name = "delta"
    category = "cli"
    profiles = ("cli",)
    cmd = "delta"
    fedora_pkg = "git-delta"


@register
class Lazygit(PackageModule):
    name = "lazygit"
    category = "cli"
    profiles = ("cli",)
    cmd = "lazygit"
    fedora_pkg = "lazygit"
    copr_repo = "atim/lazygit"


@register
class Lazydocker(PackageModule):
    name = "lazydocker"
    category = "cli"
    profiles = ("cli",)
    cmd = "lazydocker"
    fedora_pkg = "lazydocker"
    copr_repo = "atim/lazydocker"

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            copr.enable(ctx, "atim/lazydocker")
            pkg.install(ctx, "lazydocker")
        else:
            # No native apt package — use the upstream cross-distro installer.
            ctx.ex.run(
                ["sh", "-c",
                 "curl https://raw.githubusercontent.com/jesseduffield/lazydocker"
                 "/master/scripts/install_update_linux.sh | bash"]
            )


@register
class Dust(PackageModule):
    name = "dust"
    category = "cli"
    profiles = ("cli",)
    cmd = "dust"
    fedora_pkg = "rust-dust"
    debian_pkg = "du-dust"   # Ubuntu apt package name differs from Fedora


@register
class Duf(PackageModule):
    name = "duf"
    category = "cli"
    profiles = ("cli",)
    cmd = "duf"
    fedora_pkg = "duf"


@register
class Sd(PackageModule):
    name = "sd"
    category = "cli"
    profiles = ("cli",)
    cmd = "sd"
    fedora_pkg = "sd"


@register
class Yq(PackageModule):
    name = "yq"
    category = "cli"
    profiles = ("cli",)
    cmd = "yq"
    fedora_pkg = "yq"


@register
class Tealdeer(PackageModule):
    name = "tealdeer"
    category = "cli"
    profiles = ("cli",)
    cmd = "tldr"
    fedora_pkg = "tealdeer"


@register
class Fastfetch(PackageModule):
    name = "fastfetch"
    category = "cli"
    profiles = ("cli",)
    cmd = "fastfetch"
    fedora_pkg = "fastfetch"


@register
class Gh(PackageModule):
    name = "gh"
    category = "cli"
    profiles = ("cli",)
    cmd = "gh"
    fedora_pkg = "gh"
