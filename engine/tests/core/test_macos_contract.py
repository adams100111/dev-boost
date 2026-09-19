"""Every module must have a macOS answer: installable, dropped, provided, or a known gap.

KNOWN_GAPS is the M1 baseline of modules with no macOS path yet. M3–M5 add macOS
strategies and delete names from it; it must be empty by the end of M5 (spec §9).
"""

from __future__ import annotations

from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

KNOWN_GAPS: frozenset[str] = frozenset({
    "agent-sudo",
    "android-sdk",
    "aspire",
    "aspire-gc",
    "atuin",
    "bash-config",
    "bitwarden",
    "browser-view",
    "bruno",
    "build-tools",
    "caddy",
    "chezmoi",
    "chezmoi-repo",
    "claude-code",
    "claude-mcp",
    "claude-notify",
    "claude-plugins",
    "claude-skills",
    "claude-statusline",
    "code-server",
    "codex-code",
    "codex-config",
    "codex-mcp",
    "codex-plugins",
    "codex-skills",
    "crossarch-build",
    "data-services",
    "ddev",
    "ddev-remote",
    "devops-lsp",
    "devops-tools",
    "docker",
    "docker-build-gc",
    "dotfiles",
    "dotnet-lsp",
    "dotnet-sdk",
    "dust",
    "earlyoom",
    "expo",
    "eza",
    "fastfetch",
    "flameshot",
    "fresh",
    "fresh-lsp",
    "fwupd",
    "gearlever",
    "gh",
    "ghostty",
    "gpu-detect",
    "herdr",
    "herdr-plugins",
    "jetbrains-toolbox",
    "laravel-lsp",
    "lazydocker",
    "lazygit",
    "localsend",
    "mise",
    "mosh",
    "neovim",
    "nerd-fonts",
    "obsidian",
    "obsidian-sync",
    "pi-harness",
    "playwright",
    "power-profiles-daemon",
    "python-lsp",
    "restic-b2",
    "restic-backup",
    "ripgrep",
    "sd",
    "smartmontools",
    "starship",
    "tailscale",
    "tealdeer",
    "thermald",
    "tmux-persist",
    "tpm",
    "uv",
    "va-hwaccel",
    "vlc",
    "vscode",
    "web-lsp",
    "web-runtimes",
    "wezterm",
    "yq",
    "zram",
})


def resolvable_on_macos(cls: type[Module]) -> bool:
    if cls.families and "macos" not in cls.families:
        return True  # dropped from the plan on macOS
    if "macos" in cls.provided_by:
        return True
    if cls.per_os.macos is not None:
        return True
    if issubclass(cls, PackageModule):
        # Only the base behaviour is brew-aware; a subclass that overrides install/verify
        # (COPR, curl installers, …) needs its own macOS answer.
        return cls.install is PackageModule.install and cls.verify is PackageModule.verify
    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    return cls.portable


def unresolved() -> set[str]:
    return {name for name, cls in load().items() if not resolvable_on_macos(cls)}


def test_no_new_macos_gaps() -> None:
    new = unresolved() - KNOWN_GAPS
    msg = f"modules with no macOS path (add per_os.macos / families / cask): {sorted(new)}"
    assert not new, msg


def test_known_gaps_are_still_gaps() -> None:
    fixed = KNOWN_GAPS - unresolved()
    assert not fixed, f"now resolvable — remove from KNOWN_GAPS: {sorted(fixed)}"
