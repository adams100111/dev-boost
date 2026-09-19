"""Approve pending devices, revoke devices, and track what must be rotated after a revoke."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError
from devboost.model import Ctx
from devboost.passstore import enroll, git, gpg, sync
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, Kind, RotationEntry, Store, now_iso

Confirm = Callable[[DeviceRecord], bool]

#: Commit subjects that re-encrypt without changing a secret (never count as rotation).
_AUTOMATED = ("Reencrypt password store", "devboost:")

#: A `.gpg-id` token that names a key by fingerprint / long key id (never by email).
_FP_TOKEN = re.compile(r"^(0[xX])?[0-9A-Fa-f]{16,40}$")

#: Store folders that hold no entries and must never get a `.gpg-id` of their own.
_RESERVED = (".git", ".devboost")


@dataclass(frozen=True)
class Approved:
    name: str
    scope: list[str] | None


@dataclass(frozen=True)
class Unrotated:
    device: str
    entry: str


def _pull(ctx: Ctx, store: Store) -> None:
    res = git.pull(ctx, store.root)
    if not res.ok:
        raise ConfigError(f"pass: git pull failed (exit {res.code}) — run "
                          "`devboost pass sync` (or `--resolve`) and retry")


def _require_workstation(ctx: Ctx, store: Store, device: str) -> enroll.Access:
    acc = enroll.local_access(ctx, store, device)
    if not enroll.is_workstation(acc):
        raise ConfigError("pass: approve/revoke must run on an enrolled workstation "
                          "(this device has no access to the whole store)")
    return acc


def _with(ids: list[str], fp: str) -> list[str]:
    return ids if any(gpg.matches_fingerprint(t, fp) for t in ids) else [*ids, fp]


def _pass_init(ctx: Ctx, store: Store, ids: list[str], folder: str = "") -> None:
    argv = ["pass", "init", *(["-p", folder] if folder else []), *ids]
    # Re-encryption decrypts every entry: gpg-agent may ask for the passphrase (pinentry).
    res = ctx.ex.run(argv, env=enroll.pass_env(store), interactive=True)
    if not res.ok:
        raise InstallError("pass-store", " ".join(argv), res.code)


def _gpg_id_folders(store: Store) -> list[str]:
    """Every sub-folder with its own `.gpg-id` (the store's scoped folders)."""
    out: list[str] = []
    for p in sorted(store.root.rglob(".gpg-id")):
        rel = p.parent.relative_to(store.root)
        if rel.parts and rel.parts[0] not in _RESERVED:
            out.append(rel.as_posix())
    return out


def _checked_scope(name: str, scope: list[str] | None) -> list[str] | None:
    """Validate a folder scope (it comes from the request, i.e. from the new device)."""
    if scope is None:
        return None
    if not scope:
        raise ConfigError(f"pass: refusing {name!r} — its scope is empty (a scoped device "
                          "needs at least one folder)")
    out: list[str] = []
    for folder in scope:
        p = PurePosixPath(folder.strip())
        if (not folder.strip() or not p.parts or p.is_absolute() or ".." in p.parts
                or "\\" in folder or p.parts[0] in _RESERVED):
            raise ConfigError(f"pass: refusing {name!r} — invalid scope folder {folder!r} "
                              "(use a store-relative folder such as `harness`)")
        out.append(p.as_posix())
    return out


def _checked_request(ctx: Ctx, store: Store, req: DeviceRecord,
                     scope_override: list[str] | None) -> DeviceRecord:
    """The request as it will be approved, or ConfigError if anything about it is off."""
    name = req.name
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ConfigError(f"pass: refusing request {name!r} — a device name must not contain "
                          "a path separator")
    fp = req.fingerprint.upper()
    if fp in store.revoked_fingerprints():  # I1: a revoked key never comes back, any name
        raise ConfigError(f"pass: refusing {name!r} — its key …{fp[-16:]} was revoked; the "
                          "device must enroll with a fresh key: devboost pass enroll "
                          "--name <new-name>")
    kinds: tuple[Kind, ...] = ("devices", "revoked")
    for kind in kinds:  # D17: a request must never take over a registered name
        other = store.record(kind, name)
        if other is not None and other.fingerprint.upper() != fp:
            state = "an enrolled" if kind == "devices" else "a revoked"
            raise ConfigError(f"pass: refusing {name!r} — that name already belongs to {state} "
                              f"device (key …{other.fingerprint[-16:]}); re-request under "
                              "another name: devboost pass enroll --name <name>")
    try:
        shown = gpg.show_key_file(ctx, store.key_path("pending", name))
    except InstallError:
        shown = []  # unreadable key file: refused below like a mismatching one
    if len(shown) != 1 or shown[0].fingerprint.upper() != fp:
        raise ConfigError(f"pass: refusing {name!r} — its key file does not match the "
                          "fingerprint in its request")
    scope = _checked_scope(name, req.scope)
    if scope_override is not None:
        scope = _checked_scope(name, scope_override)
    return req.model_copy(update={"scope": scope, "fingerprint": fp})


def approve(
    ctx: Ctx,
    store: Store,
    device: str,
    name: str | None,
    confirm: Confirm,
    *,
    scope_override: list[str] | None = None,
) -> list[Approved]:
    _pull(ctx, store)
    _require_workstation(ctx, store, device)
    enroll.import_device_keys(ctx, store)  # D7: `pass init` must encrypt to every device
    pending = store.records("pending")
    if name is not None:
        pending = [r for r in pending if r.name == name]
        if not pending:
            raise ConfigError(f"pass: no pending request named {name!r}")
    done: list[Approved] = []
    for req in pending:
        try:
            rec = _checked_request(ctx, store, req, scope_override)
        except ConfigError as e:
            if name is not None:
                raise
            log.warn(f"{e} — skipped")
            continue
        scope = rec.scope
        if not confirm(rec):
            log.skip(f"pass: {rec.name} not approved")
            continue
        gpg.import_trusted(ctx, store.key_path("pending", rec.name), rec.fingerprint)
        if scope is None:
            _pass_init(ctx, store, _with(store.gpg_ids(), rec.fingerprint))
            # A workstation reads everything: scoped folders list their own ids — add it there.
            for folder in _gpg_id_folders(store):
                _pass_init(ctx, store, _with(store.gpg_ids(folder), rec.fingerprint), folder)
        else:
            for folder in scope:
                base = store.gpg_ids(folder) or store.gpg_ids()
                _pass_init(ctx, store, _with(base, rec.fingerprint), folder)
        armored = store.key_path("pending", rec.name).read_text(encoding="utf-8")
        store.move("pending", "devices", rec.name)
        store.write_record("devices", rec.model_copy(update={"enrolled_at": now_iso()}), armored)
        sync.remember_devices([rec.fingerprint])  # approved here: no tripwire notice
        enroll.publish(ctx, store, f"devboost: enroll {rec.name}")
        done.append(Approved(rec.name, scope))
    return done


def rotation_entries(ctx: Ctx, store: Store, key: KeyInfo,
                     scope: list[str] | None) -> list[str]:
    """Entries the key could decrypt at any point (D9) — git history keeps them readable."""
    token = next((t for t in store.gpg_ids() if gpg.matches_fingerprint(t, key.fingerprint)), None)
    start = git.first_commit_with(ctx, store.root, token) if token and not scope else None
    if start:
        files = set(git.files_at(ctx, store.root, start)) | set(
            git.added_since(ctx, store.root, start))
    else:
        files = set(git.all_history_files(ctx, store.root))
    names = sorted(f.removesuffix(".gpg") for f in files
                   if f.endswith(".gpg") and not f.startswith(".devboost/"))
    if scope:
        names = [n for n in names if any(n.startswith(f.rstrip("/") + "/") for f in scope)]
    return names


def _subfolders_listing(store: Store, key: KeyInfo) -> list[str]:
    return [f for f in _gpg_id_folders(store)
            if any(gpg.matches_fingerprint(t, key.fingerprint) for t in store.gpg_ids(f))]


def _require_fingerprint_ids(store: Store, name: str) -> None:
    """Refuse to revoke while any `.gpg-id` names keys by email: such a token may resolve
    to the revoked key, and it would survive the re-encryption."""
    for folder in ["", *_gpg_id_folders(store)]:
        bad = [t for t in store.gpg_ids(folder) if not _FP_TOKEN.match(t)]
        if bad:
            path = store.gpg_id_path(folder)
            raise ConfigError(f"pass: refusing to revoke {name!r} — {path} names keys by "
                              f"{', '.join(bad)}; replace the email ids in {path} with "
                              "fingerprints (`pass init [-p <folder>] <fpr>…`), then retry")


def revoke(ctx: Ctx, store: Store, device: str, name: str,
           confirm: Confirm) -> RotationEntry | None:
    _pull(ctx, store)
    me = _require_workstation(ctx, store, device)
    enroll.import_device_keys(ctx, store)  # D7: `pass init` must encrypt to every device
    rec = store.record("devices", name)
    if rec is None:
        raise ConfigError(f"pass: no enrolled device named {name!r}")
    fp = rec.fingerprint.upper()
    if me.key is not None and me.key.fingerprint.upper() == fp:
        raise ConfigError("pass: refusing to revoke this device — run the revoke from "
                          "another enrolled device")
    _require_fingerprint_ids(store, name)
    earlier = store.rotation()  # a malformed rotation.json refuses now, before any change
    if not confirm(rec):
        return None
    key = KeyInfo(fp, ())
    entries = rotation_entries(ctx, store, key, rec.scope)
    root = store.gpg_ids()
    remaining = [t for t in root if not gpg.matches_fingerprint(t, key.fingerprint)]
    if len(remaining) != len(root):
        _pass_init(ctx, store, remaining)
    for folder in _subfolders_listing(store, key):
        left = [t for t in store.gpg_ids(folder) if not gpg.matches_fingerprint(t, key.fingerprint)]
        # Nothing folder-specific left → drop its .gpg-id so it inherits the root set again.
        same = set(left) == set(remaining)
        _pass_init(ctx, store, left if left and not same else [""], folder)
    entry = RotationEntry(device=name, fingerprint=fp, revoked_at=now_iso(),
                          after=git.head(ctx, store.root), entries=entries)
    store.move("devices", "revoked", name)
    store.write_rotation([*earlier, entry])
    enroll.publish(ctx, store, f"devboost: revoke {name}")
    return entry


def unrotated(ctx: Ctx, store: Store) -> list[Unrotated]:
    out: list[Unrotated] = []
    for r in store.rotation():
        for e in r.entries:
            if not (store.root / f"{e}.gpg").exists():
                continue  # deleted from the store since — nothing left to rotate here
            subjects = git.subjects_touching(ctx, store.root, r.after, f"{e}.gpg")
            if not any(not s.startswith(_AUTOMATED) for s in subjects):
                out.append(Unrotated(r.device, e))
    return out
