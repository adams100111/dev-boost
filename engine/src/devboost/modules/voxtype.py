"""voxtype — local push-to-talk dictation (MIT), on every OS (spec §2).

macOS: the peteonrails tap cask, then upstream's `voxtype setup app-bundle`, which wraps
the daemon in /Applications/Voxtype.app with a Login Item. Upstream warns that a plain
launchd service never receives Microphone access (D14). Linux: the upstream RPM/DEB
(pinned + hashed in catalog.toml), or the AUR on Arch, or the raw binary on aarch64, plus
a systemd user service. Omarchy ships it through its own menu (provided_by).

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
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.media.catalog import ReleaseAsset, voxtype_pin
from devboost.model import Ctx, Module, TccGrant
from devboost.modules.macos import Homebrew
from devboost.modules.shell import Dotfiles

CASK = "peteonrails/voxtype/voxtype"
#: `brew list --cask` rejects a tap-qualified name (exit 1 even when installed).
_CASK_SHORT = "voxtype"
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
    """Fetch *name* with voxtype, then hold it to its pinned SHA-256 (skipped if present)."""
    path = model_file(name)
    if path.exists():
        return
    res = ctx.ex.run(["voxtype", "setup", "--download", "--model", name, "--quiet"])
    if not res.ok:
        raise InstallError("voxtype", f"voxtype setup --download --model {name}", res.code)
    if not path.is_file():
        raise InstallError(
            "voxtype", f"model {name}: not found at {path} after the download", 1
        )
    want = MODEL_SHA256.get(name)
    if want is None:
        return
    if _sha256(path) != want:
        path.unlink()
        raise InstallError("voxtype", f"model {name}: sha256 mismatch, file removed", 1)


# --- macOS ---------------------------------------------------------------------------------


def _bundle_version() -> str | None:
    try:
        with (APP_BUNDLE / "Contents" / "Info.plist").open("rb") as f:
            value = plistlib.load(f).get("CFBundleShortVersionString")
    except (OSError, plistlib.InvalidFileException, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _bundle_current(ctx: Ctx) -> bool:
    """Voxtype.app exists and holds the installed version.

    `setup app-bundle` COPIES the brew binary into the bundle, so after a `brew upgrade`
    the Login Item keeps running the old one until the bundle is rebuilt.
    """
    have = _bundle_version()
    if have is None:
        return False
    res = ctx.ex.run(["voxtype", "--version"])
    m = _VERSION_RE.search(res.stdout) if res.ok else None
    return m is not None and m.group(0) == have


@dataclass(frozen=True)
class MacosVoxtype:
    #: Read by the Homebrew contract tests: this strategy installs through brew.
    uses_brew: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.cask_installed(ctx, _CASK_SHORT)
            and model_file(MODEL).exists()
            and _bundle_current(ctx)
        )

    def install(self, ctx: Ctx) -> None:
        if ctx.force and pkg.cask_installed(ctx, _CASK_SHORT):
            pkg.upgrade_cask(ctx, CASK)  # a no-op (exit 0) when already current
        else:
            pkg.install_cask(ctx, CASK)
        download_model(ctx, MODEL)
        # Only when missing or stale: the command also resets the Accessibility and Input
        # Monitoring grants, re-adds the Login Item and launches the app (M5-D6).
        if _bundle_current(ctx):
            return
        res = ctx.ex.run(["voxtype", "setup", "app-bundle"])
        if not res.ok:
            raise InstallError("voxtype", "voxtype setup app-bundle", res.code)


# --- Linux ---------------------------------------------------------------------------------


def _fetch_verified(ctx: Ctx, asset: ReleaseAsset, dest: Path) -> None:
    """Download *asset* to *dest* and check its SHA-256, unprivileged.

    A mismatch deletes the file and fails the `set -e` script, so nothing unverified is
    ever handed to the (root) package manager.
    """
    d, u, h = shlex.quote(str(dest)), shlex.quote(asset.url), shlex.quote(asset.sha256)
    script = (
        "set -e\n"
        f"curl -fL --proto '=https' --retry 2 -o {d} {u}\n"
        f"printf '%s  %s\\n' {h} {d} | sha256sum -c - "
        f"|| {{ rm -f {d}; exit 1; }}\n"
    )
    res = ctx.ex.run(["sh", "-c", script])
    if not res.ok:
        raise InstallError("voxtype", "download or checksum verification failed", res.code)


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
        if ctx.os.arch != "aarch64" and self.kind == "aur":
            pkg.install_aur(ctx, "voxtype-bin")  # maintained by the upstream author
            return
        pin = voxtype_pin()
        if ctx.os.arch == "aarch64":  # no RPM/DEB/AUR build for arm64 Linux
            key, name = "bin-aarch64", "voxtype"
        else:
            key, name = f"{self.kind}-x86_64", f"voxtype.{self.kind}"
        tmp = Path(tempfile.mkdtemp(prefix="devboost-voxtype-"))
        try:
            dest = tmp / name
            _fetch_verified(ctx, pin.assets[key], dest)
            if name == "voxtype":
                target = _home() / ".local" / "bin" / "voxtype"
                res = ctx.ex.run(["install", "-Dm755", str(dest), str(target)])
                if not res.ok:
                    raise InstallError("voxtype", f"install {target}", res.code)
            else:
                pkg.install(ctx, str(dest))  # dnf/apt-get install -y <verified file>
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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
    requires = (Homebrew,)  # dropped from Linux plans (families = macos)
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
