"""shell profile — starship, ghostty (default), wezterm (opt-in), fonts, dotfiles, bash/zsh."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.core.settings import settings
from devboost.exec.primitives import copr, flatpak, pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules.base import Chezmoi
from devboost.modules.cli_tools import Atuin, Direnv, Zoxide

_NF_VERSION = "v3.2.1"
_NF_URL = (
    f"https://github.com/ryanoasis/nerd-fonts/releases/download/{_NF_VERSION}/JetBrainsMono.zip"
)


def _home() -> Path:
    return Path(os.environ["HOME"])


#: Every dev-boost managed dotfile carries this marker (dot_zshrc, dot_bashrc, …).
_MANAGED_MARKER = "devboost — managed by chezmoi"
#: macOS login/rc files the dotfiles take over (spec §3). A pre-existing one that is not
#: dev-boost's is kept aside before `chezmoi apply --force` overwrites it.
_TAKEN_OVER = (".zshrc", ".zprofile", ".bash_profile")


def keep_foreign_rc_files(home: Path) -> list[Path]:
    """Copy each foreign rc file to ``<name>.pre-devboost`` and return the backups.

    A copy, not a move: the original stays in place until ``chezmoi apply --force``
    replaces it, so a failed apply never leaves the Mac without its ``~/.zprofile``
    (brew's PATH). A symlink is copied as the link itself, never followed.

    An earlier backup is never replaced: a later foreign file becomes
    ``<name>.pre-devboost.1``, ``.2``, … Content is not merged — the managed files source
    ``~/.zshrc.local`` / ``~/.zprofile.local`` for machine-specific lines.
    """
    kept: list[Path] = []
    for name in _TAKEN_OVER:
        path = home / name
        if not (path.is_file() or path.is_symlink()):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""  # a dangling symlink: nothing of ours, keep it too
        if _MANAGED_MARKER in text:
            continue
        backup = home / f"{name}.pre-devboost"
        n = 0
        while backup.exists() or backup.is_symlink():
            n += 1
            backup = home / f"{name}.pre-devboost.{n}"
        shutil.copy2(path, backup, follow_symlinks=False)
        kept.append(backup)
    return kept


@register
class Starship(Module):
    name = "starship"
    category = "shell"
    description = "Cross-shell prompt."
    profiles = ("shell",)
    per_os = OsMap(macos=BrewFormula("starship"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("starship")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # Not in Ubuntu apt OR Fedora's default repos — the official installer drops the binary
        # into ~/.local/bin (on PATH), no sudo, on any distro. The installer's -b doesn't create
        # the dir, so ensure it exists (fresh boxes may not have ~/.local/bin yet).
        bindir = _home() / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(
            ["sh", "-c",
             f"curl -sS https://starship.rs/install.sh | sh -s -- -y -b {bindir}"]
        )


_WEZTERM_APPIMAGE = (
    "https://github.com/wezterm/wezterm/releases/download/nightly/"
    "WezTerm-nightly-Ubuntu20.04.AppImage"
)


@register
class Wezterm(Module):
    name = "wezterm"
    category = "shell"
    description = (
        "GPU terminal + multiplexer (nightly) — opt-in, deprecated: Ghostty is the default "
        "and herdr the multiplexer."
    )
    gui = True
    profiles = ("optional-terminals",)
    # Omarchy ships foot as the default terminal, themed by `omarchy theme set` and
    # routed through xdg-terminal-exec. Installing a second "default terminal" fights
    # the platform's theming and its terminal-launch chain.
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)
    # macOS: the nightly cask (the last stable release is Feb 2024).
    per_os = OsMap(macos=BrewCask("wezterm@nightly"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("wezterm")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # Nightly AppImage extracted into ~/.local (no FUSE, no sudo). The COPR
        # lacks builds for newer Fedora releases, so the AppImage is the reliable
        # path on both Fedora and Ubuntu. Symlinked onto PATH + a desktop entry.
        home = _home()
        bindir = home / ".local" / "bin"
        appdir = home / ".local" / "wezterm-nightly"
        script = f"""set -e
tmp=$(mktemp -d)
curl -fL --retry 2 -o "$tmp/wez.AppImage" "{_WEZTERM_APPIMAGE}"
chmod +x "$tmp/wez.AppImage"
(cd "$tmp" && ./wez.AppImage --appimage-extract >/dev/null)
rm -rf "{appdir}"
mv "$tmp/squashfs-root" "{appdir}"
mkdir -p "{bindir}"
ln -sf "{appdir}/AppRun" "{bindir}/wezterm"
rm -rf "$tmp"
icon=$(find "{appdir}" -maxdepth 4 -name org.wezfurlong.wezterm.png | head -1)
if [ -n "$icon" ]; then
  mkdir -p "$HOME/.local/share/icons/hicolor/128x128/apps"
  cp "$icon" "$HOME/.local/share/icons/hicolor/128x128/apps/"
fi
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/org.wezfurlong.wezterm.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=WezTerm
GenericName=Terminal
Exec={bindir}/wezterm start --cwd .
TryExec={bindir}/wezterm
Icon=org.wezfurlong.wezterm
Terminal=false
Categories=System;TerminalEmulator;
StartupWMClass=org.wezfurlong.wezterm
DESKTOP
"""
        ctx.ex.run(["sh", "-c", script])


@register
class Ghostty(Module):
    name = "ghostty"
    category = "shell"
    description = "GPU-accelerated terminal — the default on every OS (Omarchy keeps foot)."
    gui = True
    profiles = ("shell",)
    # Omarchy ships foot as the default terminal, themed by `omarchy theme set` and
    # routed through xdg-terminal-exec. Installing a second "default terminal" fights
    # the platform's theming and its terminal-launch chain.
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)
    # macOS: the cask is the app bundle (no CLI on PATH), so verify asks brew.
    per_os = OsMap(macos=BrewCask("ghostty"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        if ctx.os.family == "debian":
            return "com.mitchellh.ghostty" in ctx.ex.run(
                ["flatpak", "list", "--app", "--columns=application"]
            ).stdout
        return ctx.ex.which("ghostty")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
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
    # Omarchy ships ttf-jetbrains-mono-nerd-basic and manages fonts via `omarchy font set`.
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)
    gui = True  # a display concern — on a headless server glyphs render in the CLIENT's
    # terminal, not here, and fontconfig may be absent (fc-list then fails verify). Skip it
    # on headless boxes (→ "skip nerd-fonts (headless)") rather than erroring.
    profiles = ("shell",)
    # macOS: the Homebrew font cask (tracks the latest Nerd Fonts; Linux pins v3.2.1).
    per_os = OsMap(macos=BrewCask("font-jetbrains-mono-nerd-font"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return "JetBrainsMono Nerd Font" in ctx.ex.run(["fc-list"]).stdout

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
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
    # Runs unchanged on macOS: chezmoi comes from brew, and the source picks each OS's
    # files itself (.chezmoiignore). install() also keeps foreign zsh/bash rc files.
    portable = True

    def _stamp(self) -> Path:
        return _home() / ".config" / "devboost" / "dotfiles.sha256"

    @staticmethod
    def _source_digest(src: Path) -> str:
        # Content+name digest of the bundled dotfiles source: changes when a release
        # updates a dotfile, stable otherwise. Reliable and SYMMETRIC with apply —
        # unlike `chezmoi verify`, which false-positived drift right after a clean apply
        # (source mode), reporting "verify failed after install" and blocking dependents.
        h = hashlib.sha256()
        for p in sorted(src.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(src).as_posix().encode())
                h.update(b"\0")
                h.update(p.read_bytes())
        return h.hexdigest()

    def verify(self, ctx: Ctx) -> bool:
        # In sync iff the stamp matches the current source digest. After an update
        # changes the bundled dotfiles the digest differs → re-apply on next install
        # (so config changes propagate without --force); stays in sync afterwards.
        src = settings.root / "dotfiles"
        if not src.is_dir():
            return True  # no source to apply → nothing to do
        stamp = self._stamp()
        return (
            stamp.is_file()
            and stamp.read_text(encoding="utf-8").strip() == self._source_digest(src)
        )

    def install(self, ctx: Ctx) -> None:
        src = settings.root / "dotfiles"
        if not src.is_dir():
            log.warn(f"dotfiles: source not found ({src}) — skipping")
            return
        if ctx.os.family == "macos":
            for backup in keep_foreign_rc_files(_home()):
                log.ok(
                    f"dotfiles: kept your previous ~/{backup.name.split('.pre-devboost')[0]}"
                    f" as ~/{backup.name} — machine-specific lines belong in"
                    " ~/.zshrc.local or ~/.zprofile.local"
                )
        # --force: apply without prompting. The dotfiles are the source of truth, so
        # local drift (e.g. btop/atuin rewriting their own config at runtime) must be
        # overwritten silently. Without it, chezmoi tries to prompt on /dev/tty for any
        # changed target; under devboost's captured stdout that prompt blocks forever
        # (observed: a `chezmoi apply` hung 90+ min holding the state lock, so nothing
        # — including atuin — ever finished configuring).
        res = ctx.ex.run(
            ["chezmoi", "apply", "--force", "--source", str(src), "--destination", str(_home())]
        )
        if not res.ok:
            raise InstallError("chezmoi", "chezmoi apply", res.code)
        stamp = self._stamp()
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(self._source_digest(src) + "\n", encoding="utf-8")
        # Reload a LIVE tmux server so config changes (status bar, gauges, keybinds, tab
        # position) take effect now. A long-lived server reads ~/.tmux.conf only at start, so
        # without this an update silently keeps stale config until the server is killed —
        # exactly why gauges/tabs looked "broken" after an update. `tmux info` exits non-zero
        # when no server is running, so this is a no-op on a box that isn't using tmux yet.
        if ctx.ex.which("tmux") and ctx.ex.run(["tmux", "info"]).ok:
            ctx.ex.run(["tmux", "source", str(_home() / ".tmux.conf")])


#: The one line dev-boost adds to a distro-owned ~/.bashrc. Guarded so a shell still
#: starts cleanly if the fragment is ever missing.
_SHELL_FRAGMENT = ".config/devboost/shell.bash"
_SOURCE_MARKER = 'source "${HOME}/' + _SHELL_FRAGMENT + '"'
_SOURCE_BLOCK = (
    "\n# >>> devboost >>>\n"
    "# dev-boost's shell config (prompt, history, tool init, dev/expose/pw-* helpers).\n"
    "# Appended rather than replacing this file, because Omarchy owns ~/.bashrc.\n"
    '[[ -r "${HOME}/' + _SHELL_FRAGMENT + '" ]] && ' + _SOURCE_MARKER + "\n"
    "# <<< devboost <<<\n"
)


@register
class BashConfig(Module):
    name = "bash-config"
    category = "shell"
    description = "Wire dev-boost's bash init into ~/.bashrc (appending where the OS owns it)."
    requires = (Dotfiles,)
    profiles = ("shell",)
    # bash is the interactive shell on Linux only; macOS runs zsh (zsh-config).
    families: ClassVar[tuple[str, ...]] = ("fedora", "debian", "arch")

    def _owns_bashrc(self, ctx: Ctx) -> bool:
        """True when dev-boost's own dotfiles supply ~/.bashrc wholesale.

        On Omarchy the distro owns the file — it bootstraps OMARCHY_PATH and sources the
        Omarchy rc, and `.chezmoiignore` keeps chezmoi's hands off it — so dev-boost has to
        append its one source line instead of writing the file.
        """
        return ctx.os.distro != "omarchy"

    def verify(self, ctx: Ctx) -> bool:
        bashrc = _home() / ".bashrc"
        if not bashrc.exists():
            return False
        text = bashrc.read_text(encoding="utf-8")
        if not self._owns_bashrc(ctx):
            # Satisfied once the fragment exists AND the distro's bashrc sources it.
            return (_home() / _SHELL_FRAGMENT).is_file() and _SOURCE_MARKER in text
        return "devboost" in text and (
            "starship init bash" in text or _SOURCE_MARKER in text
        )

    def install(self, ctx: Ctx) -> None:
        if self._owns_bashrc(ctx):
            # The bashrc content is applied by the dotfiles module (this is a marker check).
            return
        bashrc = _home() / ".bashrc"
        text = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
        if _SOURCE_MARKER in text:
            return  # idempotent — never append the block twice
        bashrc.parent.mkdir(parents=True, exist_ok=True)
        with bashrc.open("a", encoding="utf-8") as fh:
            fh.write(_SOURCE_BLOCK)
        log.ok("bash-config: sourced dev-boost's shell fragment from ~/.bashrc")


@register
class ZshPlugins(Module):
    name = "zsh-plugins"
    category = "shell"
    description = "zsh-autosuggestions + zsh-syntax-highlighting (sourced by shell.zsh)."
    profiles = ("shell",)
    # zsh is the interactive shell only on macOS (bash on Linux) — spec §2.
    families: ClassVar[tuple[str, ...]] = ("macos",)
    self_updating = True  # `devboost install --update` → brew upgrade
    per_os = OsMap(macos=BrewFormula("zsh-autosuggestions", "zsh-syntax-highlighting"))


#: The line dot_zshrc uses to load dev-boost's zsh config (checked by zsh-config).
_ZSH_SOURCE_LINE = (
    '[[ -r "${HOME}/.config/devboost/shell.zsh" ]] && source "${HOME}/.config/devboost/shell.zsh"'
)


@register
class ZshConfig(Module):
    name = "zsh-config"
    category = "shell"
    description = "Check dev-boost's zsh config is live (~/.zshrc → shell.zsh) — macOS."
    requires = (Dotfiles, ZshPlugins)
    profiles = ("shell",)
    families: ClassVar[tuple[str, ...]] = ("macos",)
    # Written for macOS: it only reads the files the dotfiles module applied.
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        zshrc = _home() / ".zshrc"
        if not zshrc.is_file() or not (_home() / ".config/devboost/shell.zsh").is_file():
            return False
        text = zshrc.read_text(encoding="utf-8")
        return _MANAGED_MARKER in text and _ZSH_SOURCE_LINE in text

    def install(self, ctx: Ctx) -> None:
        # ~/.zshrc is written by the dotfiles module (a marker check, like bash-config).
        log.warn(
            "zsh-config: ~/.zshrc is not dev-boost's — run `devboost install dotfiles --force`"
        )


@register
class ClaudeStatusline(Module):
    name = "claude-statusline"
    category = "shell"
    description = "Point Claude Code's statusLine at the managed ~/.claude/statusline.sh."
    requires = (Dotfiles,)
    profiles = ("shell",)
    # A JSON merge into ~/.claude/settings.json; the script it points at is portable.
    portable = True

    def _settings_path(self) -> Path:
        return _home() / ".claude" / "settings.json"

    def _script_path(self) -> str:
        return str(_home() / ".claude" / "statusline.sh")

    def verify(self, ctx: Ctx) -> bool:
        path = self._settings_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        line = data.get("statusLine") if isinstance(data, dict) else None
        return isinstance(line, dict) and line.get("command") == self._script_path()

    def install(self, ctx: Ctx) -> None:
        # Idempotently merge the statusLine key into ~/.claude/settings.json,
        # preserving any other settings the user already has. The script itself
        # is delivered by the dotfiles module (private_dot_claude/statusline.sh).
        path = self._settings_path()
        data: dict[str, object] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warn("claude-statusline: settings.json is not valid JSON — left untouched")
                return
            if isinstance(loaded, dict):
                data = loaded
        data["statusLine"] = {
            "type": "command",
            "command": self._script_path(),
            "padding": 0,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@register
class ClaudeNotify(Module):
    name = "claude-notify"
    category = "shell"
    description = "Ping ntfy (phone) on Claude task-done / needs-input via Stop/Notification hooks."
    requires = (Dotfiles,)
    profiles = ("shell",)

    def _settings_path(self) -> Path:
        return _home() / ".claude" / "settings.json"

    def _script(self) -> str:
        # Delivered by the dotfiles module (private_dot_claude/hooks/notify.sh).
        return str(_home() / ".claude" / "hooks" / "notify.sh")

    def _group(self, arg: str) -> dict[str, object]:
        return {"hooks": [{"type": "command", "command": f"{self._script()} {arg}"}]}

    def verify(self, ctx: Ctx) -> bool:
        path = self._settings_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        hooks = data.get("hooks") if isinstance(data, dict) else None
        return isinstance(hooks, dict) and "notify.sh" in json.dumps(hooks.get("Stop", []))

    def install(self, ctx: Ctx) -> None:
        # Merge Stop + Notification hooks into ~/.claude/settings.json, preserving other keys
        # and other hook events (the notify script itself is a no-op until DEVBOOST_NTFY_URL
        # is set, so wiring the hooks is always safe).
        path = self._settings_path()
        data: dict[str, object] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warn("claude-notify: settings.json is not valid JSON — left untouched")
                return
            if isinstance(loaded, dict):
                data = loaded
        raw = data.get("hooks")
        hooks: dict[str, object] = raw if isinstance(raw, dict) else {}
        hooks["Stop"] = [self._group("done")]
        hooks["Notification"] = [self._group("input")]
        data["hooks"] = hooks
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
