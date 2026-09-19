"""Every module must have a macOS answer: installable, dropped, provided, or a known gap.

KNOWN_GAPS maps each module with no macOS path yet to the milestone that brings it.
M2 cleared the `terminal` set (the `macos` profile); M3's later tasks delete their "M3"
names as they land. "M4" names are declared `MacosPending` (Docker runtime, launchd
timers): designed, reported `blocked` on a Mac, but still gaps. The map must be empty by
the end of M5 (spec §9).
"""

from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pending import MacosPending
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

KNOWN_GAPS: dict[str, str] = {
    "agent-sudo": "M3",
    "android-sdk": "M3",
    "aspire": "M3",
    "aspire-gc": "M4",
    "bitwarden": "M3",
    "browser-view": "M3",
    "bruno": "M3",
    "build-tools": "M3",
    "caddy": "M3",
    "chezmoi-repo": "M3",
    "claude-code": "M3",
    "claude-mcp": "M3",
    "claude-notify": "M3",
    "claude-plugins": "M3",
    "claude-skills": "M3",
    "code-server": "M3",
    "codex-code": "M3",
    "codex-config": "M3",
    "codex-mcp": "M3",
    "codex-plugins": "M3",
    "codex-skills": "M3",
    "crossarch-build": "M3",
    "data-services": "M3",
    "ddev": "M3",
    "ddev-remote": "M3",
    "devops-lsp": "M3",
    "devops-tools": "M3",
    "docker": "M4",
    "docker-build-gc": "M4",
    "dotnet-lsp": "M3",
    "dotnet-sdk": "M3",
    "earlyoom": "M3",
    "expo": "M3",
    "flameshot": "M3",
    "fresh-lsp": "M3",
    "fwupd": "M3",
    "gearlever": "M3",
    "gpu-detect": "M3",
    "herdr": "M3",
    "herdr-plugins": "M3",
    "jetbrains-toolbox": "M3",
    "laravel-lsp": "M3",
    "localsend": "M3",
    "mosh": "M3",
    "neovim": "M3",
    "obsidian": "M3",
    "obsidian-sync": "M4",
    "pi-harness": "M3",
    "playwright": "M3",
    "power-profiles-daemon": "M3",
    "python-lsp": "M3",
    "restic-b2": "M4",
    "restic-backup": "M4",
    "smartmontools": "M3",
    "tailscale": "M3",
    "thermald": "M3",
    "tmux-persist": "M3",
    "tpm": "M3",
    "uv": "M3",
    "va-hwaccel": "M3",
    "vlc": "M3",
    "vscode": "M3",
    "web-lsp": "M3",
    "web-runtimes": "M3",
    "zram": "M3",
}


def resolvable_on_macos(cls: type[Module]) -> bool:
    if cls.families and "macos" not in cls.families:
        return True  # dropped from the plan on macOS
    if "macos" in cls.provided_by:
        return True
    if isinstance(cls.per_os.macos, MacosPending):
        return False  # designed, but owned by a later milestone: still a known gap
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
    new = unresolved() - set(KNOWN_GAPS)
    msg = f"modules with no macOS path (add per_os.macos / families / cask): {sorted(new)}"
    assert not new, msg


def test_known_gaps_are_still_gaps() -> None:
    fixed = set(KNOWN_GAPS) - unresolved()
    assert not fixed, f"now resolvable — remove from KNOWN_GAPS: {sorted(fixed)}"


def test_later_milestone_gaps_are_the_pending_modules() -> None:
    # A gap owned by a later milestone must say so on a Mac (MacosPending), never fall
    # through to its Linux path; and every MacosPending module is listed under its owner.
    pending = {
        name: cls.per_os.macos.milestone for name, cls in load().items()
        if isinstance(cls.per_os.macos, MacosPending)
    }
    assert pending == {n: m for n, m in KNOWN_GAPS.items() if m != "M3"}


REPO_ROOT = Path(__file__).resolve().parents[3]
MAC = OsInfo("macos", "macos", "aarch64", headless=False)
FEDORA = OsInfo("fedora", "fedora", "x86_64", headless=False)


def _plan(profile: str, os_info: OsInfo, tmp_path: Path) -> list[PlannedModule]:
    modules = load()
    names = expand([profile], load_profiles(REPO_ROOT / "profiles.toml"), modules)
    return build_plan(toposort(names, modules), modules, os_info, gpu_marker=tmp_path / "none")


def test_the_macos_profile_plans_cleanly_on_a_mac(tmp_path: Path) -> None:
    modules = load()
    reasons = {p.name: p.skip_reason for p in _plan("macos", MAC, tmp_path)}
    assert not sorted(n for n in reasons if not resolvable_on_macos(modules[n]))
    assert not [n for n, r in reasons.items() if r == "unsupported-os"]
    for want in ("ghostty", "zsh-config", "zsh-plugins", "bash", "dotfiles", "starship",
                 "nerd-fonts", "fresh", "claude-statusline"):
        assert reasons.get(want, "missing") is None, want
    assert reasons["curl"] == reasons["unzip"] == "provided-by-macos"
    assert "bash-config" not in reasons and "wezterm" not in reasons


def test_the_terminal_profile_still_plans_cleanly_on_fedora(tmp_path: Path) -> None:
    reasons = {p.name: p.skip_reason for p in _plan("terminal", FEDORA, tmp_path)}
    assert not {n: r for n, r in reasons.items() if r is not None}
    assert "bash-config" in reasons and "ghostty" in reasons
    assert not {"zsh-config", "zsh-plugins", "bash"} & set(reasons)
