"""Approve pending devices, revoke devices, and track what must be rotated after a revoke."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError
from devboost.model import Ctx
from devboost.passstore import enroll, git, gpg
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, RotationEntry, Store, now_iso

Confirm = Callable[[DeviceRecord], bool]

#: Commit subjects that re-encrypt without changing a secret (never count as rotation).
_AUTOMATED = ("Reencrypt password store", "devboost:")


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


def _verify_request(ctx: Ctx, store: Store, rec: DeviceRecord) -> None:
    shown = gpg.show_key_file(ctx, store.key_path("pending", rec.name))
    if len(shown) != 1 or shown[0].fingerprint != rec.fingerprint.upper():
        raise ConfigError(f"pass: refusing {rec.name!r} — its key file does not match the "
                          "fingerprint in its request")


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
    pending = store.records("pending")
    if name is not None:
        pending = [r for r in pending if r.name == name]
        if not pending:
            raise ConfigError(f"pass: no pending request named {name!r}")
    done: list[Approved] = []
    for req in pending:
        _verify_request(ctx, store, req)
        scope = scope_override if scope_override is not None else req.scope
        rec = req.model_copy(update={"scope": scope})
        if not confirm(rec):
            log.skip(f"pass: {rec.name} not approved")
            continue
        gpg.import_trusted(ctx, store.key_path("pending", rec.name), rec.fingerprint)
        if scope is None:
            _pass_init(ctx, store, _with(store.gpg_ids(), rec.fingerprint))
        else:
            for folder in scope:
                base = store.gpg_ids(folder) or store.gpg_ids()
                _pass_init(ctx, store, _with(base, rec.fingerprint), folder)
        armored = store.key_path("pending", rec.name).read_text(encoding="utf-8")
        store.move("pending", "devices", rec.name)
        store.write_record("devices", rec.model_copy(update={"enrolled_at": now_iso()}), armored)
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
    out: list[str] = []
    for p in sorted(store.root.rglob(".gpg-id")):
        rel = p.parent.relative_to(store.root)
        if rel.parts and rel.parts[0] not in (".git", ".devboost"):
            folder = rel.as_posix()
            if any(gpg.matches_fingerprint(t, key.fingerprint) for t in store.gpg_ids(folder)):
                out.append(folder)
    return out


def revoke(ctx: Ctx, store: Store, device: str, name: str,
           confirm: Confirm) -> RotationEntry | None:
    _pull(ctx, store)
    me = _require_workstation(ctx, store, device)
    rec = store.record("devices", name)
    if rec is None:
        raise ConfigError(f"pass: no enrolled device named {name!r}")
    if me.key is not None and me.key.fingerprint == rec.fingerprint:
        raise ConfigError("pass: refusing to revoke this device — run the revoke from "
                          "another enrolled device")
    if not confirm(rec):
        return None
    key = KeyInfo(rec.fingerprint, ())
    entries = rotation_entries(ctx, store, key, rec.scope)
    root = store.gpg_ids()
    remaining = [t for t in root if not gpg.matches_fingerprint(t, key.fingerprint)]
    if len(remaining) != len(root):
        _pass_init(ctx, store, remaining)
    for folder in _subfolders_listing(store, key):
        left = [t for t in store.gpg_ids(folder) if not gpg.matches_fingerprint(t, key.fingerprint)]
        # Nothing folder-specific left → drop its .gpg-id so it inherits the root set again.
        _pass_init(ctx, store, left if left and left != remaining else [""], folder)
    entry = RotationEntry(device=name, fingerprint=rec.fingerprint, revoked_at=now_iso(),
                          after=git.head(ctx, store.root), entries=entries)
    store.move("devices", "revoked", name)
    store.write_rotation([*store.rotation(), entry])
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
