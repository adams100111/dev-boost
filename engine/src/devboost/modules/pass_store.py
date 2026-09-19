"""pass + pass-store — the credential store on every workstation (see docs/pass.md)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import DevbootError
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.core.userconfig import load_user_config
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src
from devboost.modules.cli_tools import Git
from devboost.modules.secrets import Secrets
from devboost.passstore import enroll, paths, sync
from devboost.passstore.layout import Store

#: Passphrase cached 8 h since last use, 24 h at most (spec: Linux gpg-agent cache).
AGENT_TTLS: dict[str, str] = {"default-cache-ttl": "28800", "max-cache-ttl": "86400"}

#: Homebrew's default prefix per arch — Apple Silicon /opt/homebrew, Intel /usr/local (R5).
_BREW_PREFIX: dict[str, str] = {"aarch64": "/opt/homebrew", "x86_64": "/usr/local"}
#: macOS: command → Homebrew formula (R6). pinentry-mac asks for the passphrase in a dialog
#: that can keep it in the login keychain.
MAC_FORMULAE: dict[str, str] = {"pass": "pass", "gpg": "gnupg", "pinentry-mac": "pinentry-mac"}


def gnupg_home() -> Path:
    override = os.environ.get("GNUPGHOME")
    return Path(override) if override else Path(os.environ["HOME"]) / ".gnupg"


def pinentry_mac(os_info: OsInfo) -> str:
    return f"{_BREW_PREFIX.get(os_info.arch, '/opt/homebrew')}/bin/pinentry-mac"


def agent_settings(os_info: OsInfo) -> dict[str, str]:
    """The gpg-agent.conf keys dev-boost manages: cache TTLs everywhere; on macOS also the
    pinentry-mac program (a managed key — a different pinentry-program is replaced)."""
    out = dict(AGENT_TTLS)
    if os_info.family == "macos":
        out["pinentry-program"] = pinentry_mac(os_info)
    return out


def _key(line: str) -> str | None:
    s = line.strip()
    return None if not s or s.startswith("#") else s.split(maxsplit=1)[0]


def ensure_agent_conf(path: Path, settings: Mapping[str, str]) -> bool:
    """Set `key value` lines in gpg-agent.conf, keeping every other line. True if changed."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        k = _key(ln)
        if k is not None and k in settings:
            if k not in seen:
                out.append(f"{k} {settings[k]}")
                seen.add(k)
            continue
        out.append(ln)
    out += [f"{k} {v}" for k, v in settings.items() if k not in seen]
    body = "\n".join(out) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == body:
        return False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


def agent_conf_ok(path: Path, settings: Mapping[str, str]) -> bool:
    if not path.exists():
        return False
    have = {_key(ln): ln.split(maxsplit=1)[1].strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if _key(ln) and len(ln.split(maxsplit=1)) == 2}
    return all(have.get(k) == v for k, v in settings.items())


@register
class Pass(Module):
    name = "pass"
    category = "base"
    description = ("pass password-store CLI + gpg-agent passphrase cache (8 h idle / 24 h max; "
                   "pinentry-mac on macOS).")
    profiles = ("base",)
    portable = True  # install is OS-aware: brew formulae + pinentry-mac on macOS

    def _conf(self) -> Path:
        return gnupg_home() / "gpg-agent.conf"

    @staticmethod
    def _needed(ctx: Ctx) -> dict[str, str]:
        return MAC_FORMULAE if ctx.os.family == "macos" else {"pass": "pass"}

    def verify(self, ctx: Ctx) -> bool:
        return (all(ctx.ex.which(c) for c in self._needed(ctx))
                and agent_conf_ok(self._conf(), agent_settings(ctx.os)))

    def install(self, ctx: Ctx) -> None:
        missing = [f for c, f in self._needed(ctx).items() if not ctx.ex.which(c)]
        if missing:
            pkg.install(ctx, *missing)
        if ensure_agent_conf(self._conf(), agent_settings(ctx.os)):
            res = ctx.ex.run(["gpgconf", "--reload", "gpg-agent"])
            if not res.ok:  # the new TTLs apply once gpg-agent restarts anyway
                log.warn(f"pass: `gpgconf --reload gpg-agent` failed (exit {res.code}) — the "
                         "passphrase cache settings apply after the next login")


@register
class PassStore(Module):
    name = "pass-store"
    category = "base"
    description = (
        "Shared pass store: clone, enroll/adopt this device's GPG key, push-on-commit + "
        "15-min sync (devboost pass …)."
    )
    requires = (Pass, Secrets, Git)
    profiles = ("base",)
    portable = True
    families: ClassVar[tuple[str, ...]] = ("fedora", "debian", "arch", "macos")

    def _store(self) -> Store:
        return Store(paths.store_dir())

    def verify(self, ctx: Ctx) -> bool:
        store = self._store()
        if not store.is_clone():
            return False
        if not (sync.hook_installed(store)
                and sync.scheduler_installed(ctx, paths.devboost_bin())):
            return False
        try:
            acc = enroll.local_access(ctx, store, paths.device_name())
        except DevbootError:
            return False  # bad config / gpg trouble: install runs and reports the failure
        return acc.state == "enrolled" and acc.record is not None

    def install(self, ctx: Ctx) -> None:
        cfg = load_user_config()
        store = self._store()
        enroll.ensure_clone(ctx, store, paths.pass_repo(cfg))
        bin_ = paths.devboost_bin()
        # Sync is wired BEFORE enrollment: a pending device learns of its approval by itself.
        sync.install_hook(ctx, store, bin_)
        sync.install_scheduler(ctx, bin_)
        enroll.import_device_keys(ctx, store)
        enroll.ensure_access(ctx, store, paths.device_name(cfg),
                             interactive=creds_src.is_interactive())
