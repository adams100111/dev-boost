"""Recipient audit: is every entry encrypted to exactly the keys its `.gpg-id` names?

An entry written on a device with a stale `.gpg-id` — for instance inserted offline after a
revoke — stays encrypted to the old key set, and no re-encryption ever touched it. The audit
reads each entry's recipients from its packets (`gpg --list-only --list-packets`): nothing
is decrypted, so it never needs a passphrase and never opens pinentry.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from devboost.core.errors import InstallError
from devboost.model import Ctx
from devboost.passstore import gpg
from devboost.passstore.layout import Kind, Store

# revoked first: a still-current devices/pending record must never be able to relabel — or,
# via a forged key file, reclaim — a key id a revoked record already legitimately owns.
_KINDS: tuple[Kind, ...] = ("revoked", "devices", "pending")
UNREADABLE = "<unreadable>"


@dataclass(frozen=True)
class Mismatch:
    entry: str
    extra: tuple[str, ...]    # recipients the entry's .gpg-id does not name (labels)
    missing: tuple[str, ...]  # .gpg-id keys the entry is not encrypted to (labels)
    revoked: bool = False     # a currently-revoked key is among the entry's recipients


@dataclass(frozen=True)
class Report:
    mismatches: list[Mismatch]
    unauditable: list[str]  # folders whose .gpg-id names a key by email: cannot be checked


def _owners(ctx: Ctx, store: Store) -> dict[str, str]:
    """Key id → primary fingerprint: the keyring, plus the store's own key files — so a
    revoked key (deleted from the keyring by sync) is still recognised. A key file only
    vouches for the fingerprint its record names: a pushed `.asc` cannot rename a key.

    A key id two different primaries claim (e.g. a forged file binding another record's
    real subkey under its own primary — valid OpenPGP, no back-sig needed) is ambiguous:
    it is dropped rather than resolved to either primary's name."""
    ids: dict[str, str] = {}
    ambiguous: set[str] = set()

    def claim(kid: str, fp: str) -> None:
        if kid in ambiguous:
            return
        prev = ids.get(kid)
        if prev is None:
            ids[kid] = fp
        elif prev != fp:
            ambiguous.add(kid)
            del ids[kid]

    for kid, fp in gpg.key_ids(ctx).items():
        claim(kid, fp)
    for kind in _KINDS:
        for rec in store.records(kind):
            try:
                found = gpg.key_ids_in_file(ctx, store.key_path(kind, rec.name))
            except InstallError:
                continue
            for kid, fp in found.items():
                if fp == rec.fingerprint.upper():
                    claim(kid, fp)
    return ids


def _labels(store: Store) -> dict[str, str]:
    out: dict[str, str] = {}
    for kind in _KINDS:
        suffix = "" if kind == "devices" else f" ({kind})"
        for rec in store.records(kind):
            out.setdefault(rec.fingerprint.upper(), f"{rec.name}{suffix}")
    return out


def audit(ctx: Ctx, store: Store) -> Report:
    owners = _owners(ctx, store)
    labels = _labels(store)
    revoked_fps = store.revoked_fingerprints()
    mismatches: list[Mismatch] = []
    unauditable: set[str] = set()
    for entry in store.entries():
        folder = store.governing_folder(entry)
        tokens = store.gpg_ids(folder)
        if not tokens or not all(gpg.is_key_token(t) for t in tokens):
            unauditable.add(folder or ".")
            continue
        try:
            got = gpg.recipients(ctx, store.root / f"{entry}.gpg")
        except InstallError:
            mismatches.append(Mismatch(entry, (UNREADABLE,), ()))
            continue
        # an unknown or ambiguous key stays a bare key id — never a friendly name
        fps = {owners.get(kid, kid) for kid in got}
        extra = sorted(labels.get(fp, fp) for fp in fps
                       if not any(gpg.matches_fingerprint(t, fp) for t in tokens))
        missing = sorted(labels.get(t.upper(), t) for t in tokens
                         if not any(gpg.matches_fingerprint(t, fp) for fp in fps))
        if extra or missing:
            mismatches.append(Mismatch(entry, tuple(extra), tuple(missing),
                                        bool(fps & revoked_fps)))
    return Report(mismatches, sorted(unauditable))


def fix_hint(store: Store, m: Mismatch) -> str:
    """R11: `pass init` with the same ids re-encrypts exactly the entries that differ; a
    revoked recipient could read this entry's old ciphertext, so its secret must change.

    Folder and entry names are attacker-controlled (anyone with push access), so they're
    shell-quoted before landing in a copy-pasteable command."""
    folder = store.governing_folder(m.entry)
    ids = " ".join(store.gpg_ids(folder))
    scope = f"-p {shlex.quote(folder)} " if folder else ""
    init = f"pass init {scope}{ids}"
    if m.revoked:
        return f"{init}, then change the secret: pass edit {shlex.quote(m.entry)}"
    return init
