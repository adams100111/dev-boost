"""voxtype — local push-to-talk dictation (MIT), on every OS (spec §2).

macOS: the pinned universal release binary (SHA-256 in catalog.toml) in ~/.local/bin, then
upstream's `voxtype setup app-bundle`, which wraps the daemon in /Applications/Voxtype.app
with a Login Item. That step raises Automation and TCC prompts, so it runs only when
someone is at the terminal. Upstream warns that a plain launchd service never receives
Microphone access (D14). Not the peteonrails tap cask: it is stuck on 0.7.5, which reads
its config and models from ~/Library/Application Support, not the XDG paths the dotfiles
write. Linux: the upstream RPM/DEB (pinned + hashed), or the AUR on Arch, or the raw
binary on aarch64, plus a systemd user service. Omarchy ships it through its own menu
(provided_by). No step needs Homebrew, and only the Linux package/group steps need root.

Whisper models come from Hugging Face through `voxtype setup --download`, which checks
only their size and magic bytes (upstream publishes no digest for them), so each model
is re-hashed here against a pinned SHA-256 before anything counts it as installed.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import plistlib
import re
import shlex
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.core.settings import settings
from devboost.exec.primitives import pkg
from devboost.media.catalog import ReleaseAsset, voxtype_pin
from devboost.model import Ctx, Module, TccGrant
from devboost.modules import _credentials
from devboost.modules.shell import (
    _TAKEN_OVER_CONFIGS,
    Dotfiles,
    back_up_taken_over,
    record_rc_digest,
)

MODEL = "small.en"
ARABIC_MODEL = "large-v3-turbo"
BUNDLE_ID = "io.voxtype.daemon"
#: Created by `voxtype setup app-bundle`. Module attribute so tests can redirect it.
APP_BUNDLE = Path("/Applications/Voxtype.app")

#: SHA-256 of each model voxtype downloads from huggingface.co/ggerganov/whisper.cpp
#: (the Git LFS oids: GET /api/models/ggerganov/whisper.cpp/tree/main, 2026-09-19).
MODEL_SHA256: dict[str, str] = {
    "small.en": "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
    "large-v3-turbo": "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
}

#: Runtime deps per upstream docs/INSTALL.md: typing (wtype), clipboard, notifications,
#: and the ALSA→PipeWire bridge the audio capture uses.
_LINUX_DEPS: dict[str, tuple[str, ...]] = {
    "fedora": ("wtype", "wl-clipboard", "libnotify", "pipewire-alsa"),
    "debian": ("wtype", "wl-clipboard", "libnotify-bin", "pipewire-alsa"),
    "arch": ("wtype", "wl-clipboard", "libnotify", "pipewire-alsa"),
}

#: A login name usermod can take as-is: no leading '-' (it would parse as an option).
_USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9._-]*")
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+\S*")


def _home() -> Path:
    return Path(os.environ["HOME"])


def bin_path() -> Path:
    """Where the pinned binary goes (the executor puts ~/.local/bin on PATH)."""
    return _home() / ".local" / "bin" / "voxtype"


def _exe(ctx: Ctx) -> str:
    """macOS runs the pinned binary by path, so a leftover brew 0.7.5 can never shadow it."""
    return str(bin_path()) if ctx.os.family == "macos" else "voxtype"


def models_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(_home() / ".local" / "share")
    return Path(base) / "voxtype" / "models"


def model_file(name: str) -> Path:
    return models_dir() / f"ggml-{name}.bin"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download_model(ctx: Ctx, name: str) -> None:
    """Fetch *name* with voxtype and hold it to its pinned SHA-256.

    A model already on disk is re-hashed, and fetched again when it does not match (an
    interrupted run, or a file some other tool left). The download goes to a private
    directory next to the models (voxtype honours an absolute ``XDG_DATA_HOME``) and is
    renamed into place only after the hash matches, so a daemon never loads an unverified
    file. A name with no pinned digest is refused.
    """
    want = MODEL_SHA256.get(name)
    if want is None:
        raise InstallError("voxtype", f"model {name}: no pinned sha256, refusing it", 1)
    path = model_file(name)
    if path.is_file():
        if _sha256(path) == want:
            return
        log.warn(f"voxtype: {path} does not match its pinned sha256 — downloading it again")
        path.unlink()
    # voxtype falls back to a legacy ~/Library/Application Support/voxtype when the XDG
    # dir does not exist yet; creating it keeps the daemon reading where model_file() looks.
    models_dir().mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".devboost-download-", dir=models_dir()))
    try:
        res = ctx.ex.run([_exe(ctx), "setup", "--download", "--model", name, "--quiet"],
                         env={"XDG_DATA_HOME": str(tmp)})
        if not res.ok:
            raise InstallError("voxtype", f"voxtype setup --download --model {name}", res.code)
        got = tmp / "voxtype" / "models" / path.name
        if not got.is_file():
            raise InstallError(
                "voxtype", f"model {name}: not found at {got} after the download", 1
            )
        if _sha256(got) != want:
            raise InstallError("voxtype", f"model {name}: sha256 mismatch, file removed", 1)
        os.replace(got, path)  # same filesystem: atomic
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- verified downloads (both OSes) -------------------------------------------------------


def _fetch_verified(ctx: Ctx, asset: ReleaseAsset, dest: Path) -> None:
    """Download *asset* to *dest* and check its SHA-256, unprivileged.

    A mismatch deletes the file and fails the `set -e` script, so nothing unverified is
    ever installed. On macOS the quarantine flag is then removed from that verified file
    only (curl sets none today; a proxy or wrapper might).
    """
    d, u, h = shlex.quote(str(dest)), shlex.quote(asset.url), shlex.quote(asset.sha256)
    mac = ctx.os.family == "macos"
    check = "shasum -a 256 -c -" if mac else "sha256sum -c -"
    script = (
        "set -e\n"
        f"curl -fL --proto '=https' --retry 2 -o {d} {u}\n"
        f"printf '%s  %s\\n' {h} {d} | {check} || {{ rm -f {d}; exit 1; }}\n"
    )
    if mac:
        script += f"xattr -d com.apple.quarantine {d} 2>/dev/null || true\n"
    res = ctx.ex.run(["sh", "-c", script])
    if not res.ok:
        raise InstallError("voxtype", "download or checksum verification failed", res.code)


def _install_binary(ctx: Ctx, src: Path) -> None:
    target = bin_path()
    target.parent.mkdir(parents=True, exist_ok=True)  # BSD install has no -D
    res = ctx.ex.run(["install", "-m", "0755", str(src), str(target)])
    if not res.ok:
        raise InstallError("voxtype", f"install {target}", res.code)


def _with_verified(ctx: Ctx, key: str, name: str, use: Callable[[Path], None]) -> None:
    """Fetch the pinned *key* asset into a private temp dir, verify it, hand it to *use*."""
    tmp = Path(tempfile.mkdtemp(prefix="devboost-voxtype-"))  # 0700, removed below
    try:
        dest = tmp / name
        _fetch_verified(ctx, voxtype_pin().assets[key], dest)
        use(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _install_pinned_binary(ctx: Ctx, key: str) -> None:
    _with_verified(ctx, key, "voxtype", lambda src: _install_binary(ctx, src))


# --- macOS ---------------------------------------------------------------------------------


def _installed_version(ctx: Ctx) -> str | None:
    res = ctx.ex.run([_exe(ctx), "--version"])
    m = _VERSION_RE.search(res.stdout) if res.ok else None
    return m.group(0) if m else None


def _bundle_version() -> str | None:
    try:
        with (APP_BUNDLE / "Contents" / "Info.plist").open("rb") as f:
            value = plistlib.load(f).get("CFBundleShortVersionString")
    except (OSError, plistlib.InvalidFileException, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _bundle_current(ctx: Ctx) -> bool:
    """Voxtype.app exists and holds the installed version.

    `setup app-bundle` COPIES the binary into the bundle, so after an upgrade the Login
    Item keeps running the old one until the bundle is rebuilt.
    """
    have = _bundle_version()
    return have is not None and have == _installed_version(ctx)


@dataclass(frozen=True)
class MacosVoxtype:
    def verify(self, ctx: Ctx) -> bool:
        return (
            _installed_version(ctx) == voxtype_pin().version
            and model_file(MODEL).exists()
            and _bundle_current(ctx)
        )

    def install(self, ctx: Ctx) -> None:
        if ctx.force or _installed_version(ctx) != voxtype_pin().version:
            _install_pinned_binary(ctx, "bin-macos-universal")
        download_model(ctx, MODEL)
        # Only when missing or stale: the command also resets the Accessibility and Input
        # Monitoring grants, re-adds the Login Item and launches the app (M5-D6).
        if _bundle_current(ctx):
            return
        # Upstream's app-bundle step sends System Events an Apple event (Automation prompt)
        # and `open`s Voxtype.app, which asks for Accessibility, Input Monitoring and the
        # Microphone: never on a desktop nobody is watching (global constraint).
        if not _credentials.is_interactive():
            raise NeedsUser(
                "Voxtype.app needs its Login Item and permissions set up",
                "finish Voxtype setup in a terminal: `devboost install voxtype`",
            )
        res = ctx.ex.run([_exe(ctx), "setup", "app-bundle"])
        if not res.ok:
            raise InstallError("voxtype", "voxtype setup app-bundle", res.code)


# --- Linux ---------------------------------------------------------------------------------


def _desktop_user() -> str | None:
    """The login that gets the `input` group: the sudo caller, else the current user."""
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
    if user == "root" or not _USER_RE.fullmatch(user):
        return None
    return user


def _join_input_group(ctx: Ctx) -> None:
    user = _desktop_user()
    if user is None:
        log.warn("voxtype: no desktop user to add to `input`; run "
                 "`sudo usermod -aG input $USER` as that user for the hotkey")
        return
    if "input" in ctx.ex.run(["id", "-nG", user]).stdout.split():
        return
    # evdev hotkeys read /dev/input; membership applies at the next login.
    res = ctx.ex.run(["usermod", "-aG", "input", user], sudo=True)
    if not res.ok:
        raise InstallError("voxtype", f"usermod -aG input {user}", res.code)
    log.info("voxtype: log out and back in once so the `input` group (hotkey) applies")


@dataclass(frozen=True)
class LinuxVoxtype:
    kind: Literal["rpm", "deb", "aur"]

    def verify(self, ctx: Ctx) -> bool:
        return (
            ctx.ex.which("voxtype")
            and model_file(MODEL).exists()
            and ctx.ex.run(["systemctl", "--user", "is-enabled", "voxtype.service"]).ok
        )

    def _binary(self, ctx: Ctx) -> None:
        if ctx.os.arch == "aarch64":  # no RPM/DEB/AUR build for arm64 Linux
            _install_pinned_binary(ctx, "bin-aarch64")
        elif self.kind == "aur":
            pkg.install_aur(ctx, "voxtype-bin")  # maintained by the upstream author
        else:
            # dnf/apt-get install -y <verified file>: root sees only the checked package.
            _with_verified(ctx, f"{self.kind}-x86_64", f"voxtype.{self.kind}",
                           lambda path: pkg.install(ctx, str(path)))

    def install(self, ctx: Ctx) -> None:
        self._binary(ctx)
        pkg.install(ctx, *_LINUX_DEPS[ctx.os.family])
        _join_input_group(ctx)
        download_model(ctx, MODEL)
        res = ctx.ex.run(["voxtype", "setup", "systemd"])
        if not res.ok:
            raise InstallError("voxtype", "voxtype setup systemd", res.code)


@register
class Voxtype(Module):
    name = "voxtype"
    category = "base"
    description = "Voxtype — local push-to-talk dictation (Whisper small.en; MIT)."
    profiles = ("base",)
    provided_by = ("omarchy",)  # Omarchy: Install › AI › Dictation (voxtype-bin)
    gui = True
    # No Homebrew: macOS installs the pinned release binary itself.
    after = (Dotfiles,)  # the daemon should start with ~/.config/voxtype/config.toml in place
    tcc = (
        TccGrant("Microphone", "Voxtype"),
        TccGrant("ListenEvent", "Voxtype"),
        TccGrant("Accessibility", "Voxtype"),
    )
    per_os = OsMap(
        macos=MacosVoxtype(),
        fedora=LinuxVoxtype("rpm"),
        debian=LinuxVoxtype("deb"),
        arch=LinuxVoxtype("aur"),
    )


# --- voxtype-arabic (opt-in) ---------------------------------------------------------------


def arabic_marker() -> Path:
    """Read by the voxtype and AeroSpace templates (`stat`): Arabic dictation is on."""
    return _home() / ".config" / "devboost" / "voxtype-arabic"


#: The shared config, relative to HOME (a key of shell._TAKEN_OVER_CONFIGS).
_CONFIG_REL = ".config/voxtype/config.toml"


def _config_file() -> Path:
    return _home() / _CONFIG_REL


def _restart_marker() -> Path:
    """Present while the running daemon still has the old config (verify reads it)."""
    base = os.environ.get("XDG_STATE_HOME") or str(_home() / ".local" / "state")
    return Path(base) / "devboost" / "voxtype-restart-pending"


def _restart_daemon(ctx: Ctx) -> None:
    """Load the new config: clears the pending marker, or raises NeedsUser.

    macOS relaunches the Login Item app only when a human is at the terminal: the quit is
    an Apple event (it may raise an Automation prompt) and `open` launches an app (M5-D6).
    """
    ok = True
    if ctx.os.family == "macos":
        if ctx.ex.which("aerospace") and not ctx.ex.run(["aerospace", "reload-config"]).ok:
            log.warn("voxtype-arabic: `aerospace reload-config` failed — Ctrl+Alt+D is not "
                     "bound until AeroSpace reloads its config")
        if not _credentials.is_interactive():
            raise NeedsUser(
                "Voxtype must restart to load the Arabic model config",
                "quit Voxtype and reopen /Applications/Voxtype.app, or re-run "
                "`devboost install voxtype-arabic` in a terminal",
            )
        quit_ = ctx.ex.run(["osascript", "-e", f'tell application id "{BUNDLE_ID}" to quit'])
        if not quit_.ok:
            ok = False
            log.warn(f"voxtype-arabic: could not quit Voxtype ({quit_.stderr.strip()})")
        if not ctx.ex.run(["open", "-g", "-b", BUNDLE_ID]).ok:
            ok = False
            log.warn("voxtype-arabic: could not reopen Voxtype.app")
        fix = "quit Voxtype and reopen /Applications/Voxtype.app"
    else:
        if not ctx.ex.run(["systemctl", "--user", "restart", "voxtype.service"]).ok:
            ok = False
            log.warn("voxtype-arabic: `systemctl --user restart voxtype.service` failed")
        fix = "run `systemctl --user restart voxtype.service`"
    if not ok:
        raise NeedsUser("Voxtype did not restart with the Arabic model config", fix)
    _restart_marker().unlink(missing_ok=True)


@register
class VoxtypeArabic(Module):
    name = "voxtype-arabic"
    category = "base"
    description = "Arabic dictation: Whisper large-v3-turbo (1.6 GB), loaded only on demand."
    requires = (Voxtype,)
    after = (Dotfiles,)
    gui = True
    portable = True  # one install for every OS; only the daemon restart branches

    def verify(self, ctx: Ctx) -> bool:
        cfg = _config_file()
        return (
            arabic_marker().exists()
            and model_file(ARABIC_MODEL).exists()
            and cfg.is_file()
            and f'secondary_model = "{ARABIC_MODEL}"' in cfg.read_text(encoding="utf-8")
            and not _restart_marker().exists()
        )

    def install(self, ctx: Ctx) -> None:
        # macOS: the pinned binary itself (a leftover brew 0.7.5 on PATH does not count).
        present = bin_path().exists() if ctx.os.family == "macos" else ctx.ex.which("voxtype")
        if not present:
            raise NeedsUser(
                "Voxtype is not installed",
                "install it first — `devboost install voxtype` (Omarchy: menu → Install → "
                "AI → Dictation)",
            )
        # Model first: the marker switches the rendered config to it, so it must be on
        # disk (and match its pinned digest) before the config can name it.
        download_model(ctx, ARABIC_MODEL)
        marker = arabic_marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        if ctx.os.distro == "omarchy":
            self._omarchy(ctx)
            return
        home, src = _home(), settings.root / "dotfiles"
        # Same rule as the dotfiles module: a config the user changed is kept as
        # config.toml.pre-devboost before the forced apply replaces it.
        back_up_taken_over(home, src, {_CONFIG_REL: _TAKEN_OVER_CONFIGS[_CONFIG_REL]},
                           self.name)
        targets = [str(_config_file())]
        if ctx.os.family == "macos":
            targets.append(str(home / ".config" / "aerospace" / "aerospace.toml"))
        # --parent-dirs: a targeted apply fails when a target's directory does not exist yet
        # (`stat …/.config/aerospace: no such file or directory`, chezmoi 2.72).
        res = ctx.ex.run([
            "chezmoi", "apply", "--force", "--parent-dirs",
            "--source", str(src), "--destination", str(home), *targets,
        ])
        if not res.ok:
            raise InstallError("voxtype-arabic", "chezmoi apply (voxtype/aerospace config)",
                               res.code)
        try:
            record_rc_digest(home, _CONFIG_REL)  # what dev-boost wrote, for the next backup
        except OSError as exc:
            log.warn(f"voxtype-arabic: could not record the config digest ({exc})")
        restart = _restart_marker()
        restart.parent.mkdir(parents=True, exist_ok=True)
        restart.touch()
        _restart_daemon(ctx)

    @staticmethod
    def _omarchy(ctx: Ctx) -> None:
        """Omarchy owns ~/.config/voxtype (`.chezmoiignore`): never rewrite it, say how."""
        cfg = _config_file()
        if cfg.is_file() and f'secondary_model = "{ARABIC_MODEL}"' in cfg.read_text(
            encoding="utf-8"
        ):
            return
        raise NeedsUser(
            "Omarchy manages ~/.config/voxtype/config.toml, so dev-boost leaves it alone",
            f'add `secondary_model = "{ARABIC_MODEL}"` and `cold_model_timeout_secs = 60` '
            "under [whisper] in that file, then restart Voxtype from the Omarchy menu",
        )
