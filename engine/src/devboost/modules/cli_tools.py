"""The base + cli package tools — one typed declaration each (shared PackageModule).

Each tool sets: name, category, profiles, cmd (verify), fedora_pkg (install), [copr_repo].

Several tools are absent from Ubuntu's apt repos (verified against packages.ubuntu.com
for noble): atuin, eza, lazygit, dust (du-dust only lands in 25.10), yq, fastfetch, and
starship. On Debian/Ubuntu these install from the project's official installer or a
pinned GitHub release binary into ~/.local/bin (on the executor's PATH). gh uses the
official GitHub apt repo. Arch is resolved at runtime via `uname -m` so one binary built
on x86_64 CI works on both amd64 and arm64 targets.
"""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule

# --- Debian/Ubuntu install scripts (run via `sh -c`) -------------------------------------

_ATUIN_DEBIAN = (
    "set -e\n"
    "curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh -s -- --non-interactive\n"
    'mkdir -p "$HOME/.local/bin"\n'
    # The installer drops the binary in ~/.atuin/bin; symlink onto PATH so `which` finds it.
    'ln -sf "$HOME/.atuin/bin/atuin" "$HOME/.local/bin/atuin"\n'
)

_LAZYGIT_DEBIAN = (
    "set -e\n"
    'ver=$(curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest'
    " | grep -Po '\"tag_name\": *\"v\\K[^\"]*')\n"
    "arch=$(uname -m | sed 's/aarch64/arm64/')\n"
    "tmp=$(mktemp -d)\n"
    'curl -fsSL -o "$tmp/lazygit.tar.gz"'
    ' "https://github.com/jesseduffield/lazygit/releases/download/v${ver}/'
    'lazygit_${ver}_Linux_${arch}.tar.gz"\n'
    'tar -xf "$tmp/lazygit.tar.gz" -C "$tmp" lazygit\n'
    'install -Dm755 "$tmp/lazygit" "$HOME/.local/bin/lazygit"\n'
    'rm -rf "$tmp"\n'
)

_EZA_DEBIAN = (
    "set -e\n"
    'case "$(uname -m)" in\n'
    "  x86_64) t=x86_64-unknown-linux-gnu ;;\n"
    "  aarch64) t=aarch64-unknown-linux-gnu ;;\n"
    '  *) echo "eza: unsupported arch $(uname -m)" >&2; exit 1 ;;\n'
    "esac\n"
    "tmp=$(mktemp -d)\n"
    'curl -fsSL -o "$tmp/eza.tar.gz"'
    ' "https://github.com/eza-community/eza/releases/latest/download/eza_${t}.tar.gz"\n'
    'tar -xf "$tmp/eza.tar.gz" -C "$tmp"\n'
    'install -Dm755 "$tmp/eza" "$HOME/.local/bin/eza"\n'
    'rm -rf "$tmp"\n'
)

_YQ_DEBIAN = (
    "set -e\n"
    'case "$(uname -m)" in\n'
    "  x86_64) a=amd64 ;;\n"
    "  aarch64) a=arm64 ;;\n"
    '  *) echo "yq: unsupported arch $(uname -m)" >&2; exit 1 ;;\n'
    "esac\n"
    'mkdir -p "$HOME/.local/bin"\n'
    'curl -fsSL -o "$HOME/.local/bin/yq"'
    ' "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_${a}"\n'
    'chmod +x "$HOME/.local/bin/yq"\n'
)

_DUST_DEBIAN = (
    "set -e\n"
    'ver=$(curl -fsSL https://api.github.com/repos/bootandy/dust/releases/latest'
    " | grep -Po '\"tag_name\": *\"v\\K[^\"]*')\n"
    'case "$(uname -m)" in\n'
    "  x86_64) t=x86_64-unknown-linux-gnu ;;\n"
    "  aarch64) t=aarch64-unknown-linux-gnu ;;\n"
    '  *) echo "dust: unsupported arch $(uname -m)" >&2; exit 1 ;;\n'
    "esac\n"
    "tmp=$(mktemp -d)\n"
    'curl -fsSL -o "$tmp/dust.tar.gz"'
    ' "https://github.com/bootandy/dust/releases/download/v${ver}/dust-v${ver}-${t}.tar.gz"\n'
    'tar -xf "$tmp/dust.tar.gz" -C "$tmp"\n'
    'install -Dm755 "$tmp/dust-v${ver}-${t}/dust" "$HOME/.local/bin/dust"\n'
    'rm -rf "$tmp"\n'
)

# gh: the official GitHub CLI apt repo. The published key is already binary (no dearmor),
# and piping curl→tee writes it byte-safe (unlike the text-capturing apt primitive).
_GH_DEBIAN = (
    "set -e\n"
    "sudo install -dm 755 /etc/apt/keyrings\n"
    "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg"
    " | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null\n"
    "sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg\n"
    'echo "deb [arch=$(dpkg --print-architecture)'
    " signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg]"
    ' https://cli.github.com/packages stable main"'
    " | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null\n"
    # `|| true`: an unrelated broken source must not abort the install — the github-cli
    # repo still gets indexed, which is all `apt-get install gh` needs.
    "sudo apt-get update || true\n"
    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y gh\n"
)

_FASTFETCH_DEBIAN = (
    "set -e\n"
    'case "$(uname -m)" in\n'
    "  x86_64) a=amd64 ;;\n"
    "  aarch64) a=aarch64 ;;\n"
    '  *) echo "fastfetch: unsupported arch $(uname -m)" >&2; exit 1 ;;\n'
    "esac\n"
    "tmp=$(mktemp -d)\n"
    'curl -fsSL -o "$tmp/fastfetch.deb"'
    ' "https://github.com/fastfetch-cli/fastfetch/releases/latest/download/'
    'fastfetch-linux-${a}.deb"\n'
    'sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$tmp/fastfetch.deb"\n'
    'rm -rf "$tmp"\n'
)


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

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu 24.04 apt — install the latest GitHub release binary.
            ctx.ex.run(["sh", "-c", _EZA_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)


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

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu apt — official installer (→ ~/.atuin/bin, symlinked onto PATH).
            ctx.ex.run(["sh", "-c", _ATUIN_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)


@register
class Direnv(PackageModule):
    name = "direnv"
    category = "cli"
    profiles = ("cli",)
    cmd = "direnv"
    fedora_pkg = "direnv"


@register
class WlClipboard(PackageModule):
    name = "wl-clipboard"
    category = "shell"
    description = "Wayland clipboard CLI (wl-copy/wl-paste) — powers the image-paste bridge."
    profiles = ("shell",)
    cmd = "wl-paste"
    fedora_pkg = "wl-clipboard"
    debian_pkg = "wl-clipboard"
    gui = True  # laptop-only; skipped on a headless VPS


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

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu apt — install the latest GitHub release binary.
            ctx.ex.run(["sh", "-c", _LAZYGIT_DEBIAN])
        else:
            copr.enable(ctx, self.copr_repo)
            pkg.install(ctx, self.fedora_pkg)


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
    fedora_pkg = "du-dust"  # Fedora packages du-dust as `du-dust` (not `rust-dust`)

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # du-dust is not in Ubuntu apt until 25.10 — install the GitHub release binary.
            ctx.ex.run(["sh", "-c", _DUST_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)


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

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu apt — install the latest static GitHub release binary.
            ctx.ex.run(["sh", "-c", _YQ_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)


@register
class Tealdeer(PackageModule):
    name = "tealdeer"
    category = "cli"
    profiles = ("cli",)
    cmd = "tldr"
    fedora_pkg = "tealdeer"

    def verify(self, ctx: Ctx) -> bool:
        # Fedora's package provides `tldr`; Ubuntu's provides `tealdeer` (no `tldr`
        # symlink). Accept either so verify is correct on both.
        return ctx.ex.which("tldr") or ctx.ex.which("tealdeer")


@register
class Fastfetch(PackageModule):
    name = "fastfetch"
    category = "cli"
    profiles = ("cli",)
    cmd = "fastfetch"
    fedora_pkg = "fastfetch"

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu apt until 25.10 — install the upstream .deb release.
            ctx.ex.run(["sh", "-c", _FASTFETCH_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)


@register
class Gh(PackageModule):
    name = "gh"
    category = "cli"
    profiles = ("cli",)
    cmd = "gh"
    fedora_pkg = "gh"

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu apt — add the official GitHub CLI apt repo, then install.
            ctx.ex.run(["sh", "-c", _GH_DEBIAN])
        else:
            pkg.install(ctx, self.fedora_pkg)
