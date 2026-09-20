"""Getting this device access to the store: clone → classify → genesis / adopt / request.

Never automatic: a new device only *requests* access; an enrolled device approves it.
"""

from __future__ import annotations

import getpass
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError, NeedsUser
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src
from devboost.passstore import git, gpg, notify
from devboost.passstore import paths as paths_mod
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, Kind, Store, now_iso
from devboost.passstore.paths import clone_url

AccessState = Literal["no-store", "genesis", "enrolled", "pending", "new"]


@dataclass(frozen=True)
class Access:
    state: AccessState
    key: KeyInfo | None
    record: DeviceRecord | None


@dataclass(frozen=True)
class Identity:
    real_name: str
    email: str


def identity(ctx: Ctx) -> Identity:
    name = ctx.ex.run(["git", "config", "--global", "user.name"]).stdout.strip()
    email = ctx.ex.run(["git", "config", "--global", "user.email"]).stdout.strip()
    user = getpass.getuser()
    return Identity(name or user, email or f"{user}@{socket.gethostname()}")


def pass_env(store: Store) -> dict[str, str]:
    # `pass` makes its own git commits: NET_ENV never signs them (D6), never prompts.
    env = {"PASSWORD_STORE_DIR": str(store.root), **git.NET_ENV}
    try:  # pinentry-curses needs to know the terminal when gpg asks for the passphrase
        env["GPG_TTY"] = os.ttyname(0)
    except OSError:
        pass
    return env


def has_access(store: Store, key: KeyInfo, scope: list[str] | None) -> bool:
    return any(
        any(gpg.matches_fingerprint(t, key.fingerprint) for t in store.gpg_ids(f))
        for f in (scope or [""])
    )


def local_access(ctx: Ctx, store: Store, device: str) -> Access:
    if not store.is_clone():
        return Access("no-store", None, None)
    keys = gpg.secret_keys(ctx)
    if not store.gpg_ids():
        if store.entries() or store.records("devices"):  # I6: broken, not new — never re-init
            raise ConfigError(f"pass: {store.gpg_id_path()} is missing but the store holds "
                              "entries / enrolled devices — run `devboost pass sync "
                              "--resolve` to restore it")
        return Access("genesis", gpg.device_key(keys, device), None)
    by_fp = {k.fingerprint: k for k in keys}
    for rec in store.records("devices"):
        k = by_fp.get(rec.fingerprint)
        if k is not None and has_access(store, k, rec.scope):
            return Access("enrolled", k, rec)
    for k in keys:
        if has_access(store, k, None):
            return Access("enrolled", k, None)  # has access, not yet labelled → adopt
    for rec in store.records("pending"):
        k = by_fp.get(rec.fingerprint)
        if k is not None:
            return Access("pending", k, rec)
    return Access("new", gpg.device_key(keys, device), None)


def is_workstation(acc: Access) -> bool:
    """Enrolled with access to the whole store (no folder scope): may approve / revoke."""
    return acc.state == "enrolled" and not (acc.record is not None and acc.record.scope)


def ensure_clone(ctx: Ctx, store: Store, repo: str | None) -> None:
    if store.is_clone():
        return
    if store.root.exists() and (not store.root.is_dir() or any(store.root.iterdir())):
        # A real, non-empty directory already sits there — likely the user's actual data.
        # Never move/delete it ourselves: this is a human decision, so block, don't fail.
        # `pass adopt` is that decision made explicitly: it backs the directory up first.
        raise NeedsUser(
            f"{store.root} exists but is not a git clone",
            "`devboost pass adopt` moves it to <store>.pre-devboost, clones your repo in "
            "its place, and reports which entries differ — nothing is deleted. Or move "
            "the directory aside yourself and re-run.",
        )
    if repo is None:
        # Nothing to clone FROM. Blocked, not failed: naming the repo is a step for the
        # user, and there is no sensible default (paths.pass_repo).
        raise NeedsUser("no pass store repo is configured", paths_mod.NO_PASS_REPO_FIX)
    res = git.clone(ctx, clone_url(repo), store.root)
    if res.ok:
        return
    if not creds_src.gh_is_authenticated(ctx):
        raise NeedsUser("cloning the pass store needs GitHub access",
                        "gh auth login, then re-run devboost install")
    raise ConfigError(f"pass-store: cloning {repo} failed (exit {res.code}) — check pass_repo "
                      "in ~/.config/devboost/config.toml / DEVBOOST_PASS_REPO and your access")


def entry_names(root: Path) -> set[str]:
    """Every `pass` entry under *root*, by name. Names only — nothing is decrypted."""
    if not root.is_dir():
        return set()
    return {
        str(p.relative_to(root).with_suffix("")).replace(os.sep, "/")
        for p in root.rglob("*.gpg")
        if ".git" not in p.parts
    }


@dataclass(frozen=True)
class Adoption:
    """What `pass adopt` did, so the caller can report it without re-deriving anything."""

    backup: Path
    only_local: tuple[str, ...]
    only_remote: tuple[str, ...]
    shared: int


def adopt(ctx: Ctx, store: Store, repo: str | None) -> Adoption:
    """Move an existing non-clone store aside, clone *repo* in its place, and compare.

    The directory is MOVED, never deleted: if anything was only in the old copy, it is
    still on disk and the report names it. Comparison is by entry name only — telling
    whether two encrypted files hold the same secret would mean decrypting both, and GPG
    ciphertext differs every time even for identical plaintext.
    """
    if store.is_clone():
        raise ConfigError(f"pass adopt: {store.root} is already a clone — nothing to adopt")
    if repo is None:
        raise NeedsUser("no pass store repo is configured", paths_mod.NO_PASS_REPO_FIX)
    if not store.root.is_dir():
        raise ConfigError(f"pass adopt: nothing at {store.root} to adopt")

    before = entry_names(store.root)
    backup = store.root.with_name(store.root.name + ".pre-devboost")
    n = 1
    while backup.exists():
        n += 1
        backup = store.root.with_name(f"{store.root.name}.pre-devboost.{n}")
    store.root.rename(backup)

    res = git.clone(ctx, clone_url(repo), store.root)
    if not res.ok:
        backup.rename(store.root)  # put the user's data back before reporting failure
        raise ConfigError(
            f"pass adopt: cloning {repo} failed (exit {res.code}) — your store was put back "
            f"at {store.root}, nothing was lost"
        )
    after = entry_names(store.root)
    return Adoption(
        backup=backup,
        only_local=tuple(sorted(before - after)),
        only_remote=tuple(sorted(after - before)),
        shared=len(before & after),
    )


def publish(ctx: Ctx, store: Store, message: str) -> None:
    if git.commit(ctx, store.root, message):
        res = git.push(ctx, store.root)
        if not res.ok:
            log.warn(f"pass: push failed (exit {res.code}) — the sync timer will retry")


def _name_free(store: Store, name: str, fp: str | None) -> None:
    """Refuse to file *name* for key *fp* (None: no key yet) when the name belongs to a
    revoked device or another key, the key was revoked (I1), or the key is registered under
    another name."""
    if store.record("revoked", name) is not None:
        raise ConfigError(f"pass: device name {name!r} belongs to a revoked device — choose "
                          "another: devboost pass enroll --name <name>")
    kinds: tuple[Kind, ...] = ("devices", "pending")
    for kind in kinds:
        rec = store.record(kind, name)
        if rec is not None and rec.fingerprint.upper() != (fp or "").upper():
            raise ConfigError(f"pass: device name {name!r} is already used by key "
                              f"…{rec.fingerprint[-16:]} — choose another: "
                              "devboost pass enroll --name <name>")
    if fp is None:
        return
    if fp.upper() in store.revoked_fingerprints():
        raise ConfigError(f"pass: key …{fp[-16:]} was revoked and can never be enrolled again "
                          "— enroll under a new name to generate a fresh key: "
                          "devboost pass enroll --name <new-name>")
    for kind in kinds:
        other = next((r for r in store.records(kind)
                      if r.fingerprint.upper() == fp.upper() and r.name != name), None)
        if other is not None:
            raise ConfigError(f"pass: key …{fp[-16:]} is already registered as {other.name!r} "
                              f"({kind}) — use that name: devboost pass enroll --name "
                              f"{other.name}")


def _register(ctx: Ctx, store: Store, kind: Kind, name: str, fp: str,
              scope: list[str] | None) -> DeviceRecord:
    _name_free(store, name, fp)
    pending = kind == "pending"
    rec = DeviceRecord(name=name, fingerprint=fp, os=ctx.os.distro, scope=scope,
                       enrolled_at=None if pending else now_iso(),
                       requested_at=now_iso() if pending else None)
    store.write_record(kind, rec, gpg.export_armored(ctx, fp))
    return rec


def _device_fp(ctx: Ctx, key: KeyInfo | None, device: str, passphrase: str | None) -> str:
    if key is not None:
        return key.fingerprint
    ident = identity(ctx)
    return gpg.generate(ctx, gpg.device_uid(ident.real_name, ident.email, device),
                        passphrase=passphrase)


def _no_key(interactive: bool, key: KeyInfo | None, reason: str) -> None:
    if not interactive and key is None:
        raise NeedsUser(reason, "run `devboost pass enroll` in a terminal")


def ensure_access(
    ctx: Ctx,
    store: Store,
    device: str,
    *,
    interactive: bool,
    scope: list[str] | None = None,
    passphrase: str | None = None,
) -> Access:
    acc = local_access(ctx, store, device)
    if acc.state == "no-store":
        raise ConfigError(f"pass-store: {store.root} is not cloned yet")
    if acc.state == "enrolled":
        if acc.record is None and acc.key is not None:
            _register(ctx, store, "devices", device, acc.key.fingerprint, None)
            publish(ctx, store, f"devboost: adopt {device}")
            return local_access(ctx, store, device)
        return acc
    if acc.state == "pending" and acc.record is not None:
        raise NeedsUser(f"device {acc.record.name!r} is waiting for approval",
                        f"devboost pass approve {acc.record.name}")
    if acc.state == "genesis":
        _no_key(interactive, acc.key, "the pass store is empty and this device has no key yet")
        _name_free(store, device, acc.key.fingerprint if acc.key else None)
        fp = _device_fp(ctx, acc.key, device, passphrase)
        res = ctx.ex.run(["pass", "init", fp], env=pass_env(store))
        if not res.ok:
            raise InstallError("pass-store", f"pass init {fp}", res.code)
        _register(ctx, store, "devices", device, fp, None)
        publish(ctx, store, f"devboost: initialise store with {device}")
        return local_access(ctx, store, device)
    # new device: request access, then wait for an enrolled device to approve
    _no_key(interactive, acc.key, "this device has no pass key yet")
    _name_free(store, device, acc.key.fingerprint if acc.key else None)  # before any keygen
    fp = _device_fp(ctx, acc.key, device, passphrase)
    rec = _register(ctx, store, "pending", device, fp, scope)
    publish(ctx, store, f"devboost: request enrollment for {device}")
    notify.ntfy(ctx, f"pass: approve {device}?",
                f"{device} ({ctx.os.distro}) requests access, key {fp}. "
                f"On an enrolled device run: devboost pass approve {device}", priority="high")
    raise NeedsUser(f"enrollment requested for {rec.name!r}", f"devboost pass approve {rec.name}")


def import_device_keys(ctx: Ctx, store: Store) -> list[str]:
    """Import + trust every registered device key we lack, if its file and .gpg-id agree."""
    have = gpg.public_fingerprints(ctx)
    imported: list[str] = []
    revoked = store.revoked_fingerprints()
    for rec in store.records("devices"):
        if rec.fingerprint in have:
            continue
        if rec.fingerprint.upper() in revoked:
            log.warn(f"pass: {rec.name}'s key …{rec.fingerprint[-16:]} was revoked — "
                     "not imported")
            continue
        path = store.key_path("devices", rec.name)
        try:
            shown = gpg.show_key_file(ctx, path)
        except InstallError:
            shown = []  # unreadable key file: refused below like a mismatching one
        listed = has_access(store, KeyInfo(rec.fingerprint, ()), rec.scope)
        if len(shown) != 1 or shown[0].fingerprint != rec.fingerprint or not listed:
            log.warn(f"pass: {path} does not match its record / .gpg-id — not imported")
            continue
        gpg.import_trusted(ctx, path, rec.fingerprint)
        imported.append(rec.name)
    return imported
