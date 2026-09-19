"""GnuPG over the executor: list/parse keys, generate a device key, import trusted keys."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.core.errors import InstallError
from devboost.exec.executor import Result
from devboost.model import Ctx

_HEX = re.compile(r"^[0-9A-F]{16,40}$")
_ESCAPE = re.compile(r"\\x([0-9A-Fa-f]{2})")


def _unescape_uid(raw: str) -> str:
    """Undo `--with-colons` `\\xHH` escaping (notably `:` -> `\\x3a`) in the uid field."""
    return _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw)


@dataclass(frozen=True)
class KeyInfo:
    fingerprint: str
    uids: tuple[str, ...]


def parse_colons(out: str, kind: Literal["sec", "pub"]) -> list[KeyInfo]:
    """Primary-key fingerprints + uids from `--with-colons` output (subkey fprs ignored)."""
    keys: list[KeyInfo] = []
    fp: str | None = None
    uids: list[str] = []
    want_fpr = False
    for line in out.splitlines():
        f = line.split(":")
        rec = f[0]
        if rec == kind:
            if fp is not None:
                keys.append(KeyInfo(fp, tuple(uids)))
            fp, uids, want_fpr = None, [], True
        elif rec in ("sub", "ssb"):
            want_fpr = False
        elif rec == "fpr" and want_fpr and len(f) > 9:
            fp, want_fpr = f[9].upper(), False
        elif rec == "uid" and fp is not None and len(f) > 9:
            uids.append(_unescape_uid(f[9]))
    if fp is not None:
        keys.append(KeyInfo(fp, tuple(uids)))
    return keys


def _gpg(ctx: Ctx, *args: str, stdin: str | None = None, interactive: bool = False) -> Result:
    return ctx.ex.run(["gpg", "--batch", *args], stdin=stdin, interactive=interactive)


def _must(res: Result, command: str) -> Result:
    if not res.ok:
        raise InstallError("pass-store", command, res.code)
    return res


def secret_keys(ctx: Ctx) -> list[KeyInfo]:
    res = _gpg(ctx, "--with-colons", "--list-secret-keys")
    return parse_colons(res.stdout, "sec") if res.ok else []


def public_fingerprints(ctx: Ctx) -> set[str]:
    res = _gpg(ctx, "--with-colons", "--list-keys")
    return {k.fingerprint for k in parse_colons(res.stdout, "pub")} if res.ok else set()


def show_key_file(ctx: Ctx, path: Path) -> list[KeyInfo]:
    res = _gpg(ctx, "--with-colons", "--show-keys", str(path))
    return parse_colons(res.stdout, "pub") if res.ok else []


def device_uid(real_name: str, email: str, device: str) -> str:
    return f"{real_name} (devboost:{device}) <{email}>"


def device_key(keys: Sequence[KeyInfo], device: str) -> KeyInfo | None:
    tag = f"(devboost:{device})"
    return next((k for k in keys if any(tag in u for u in k.uids)), None)


def matches_fingerprint(token: str, fp: str) -> bool:
    """Does a `.gpg-id` token name the key *fp*? Full fpr or long key id (suffix, 0x ok).

    Emails deliberately never match (D4): any key can carry any uid, so an email in
    `.gpg-id` must not grant access to — or ultimate trust in — a key nobody approved.
    """
    t = token.strip().upper().removeprefix("0X")
    return bool(_HEX.match(t)) and fp.upper().endswith(t)


def _loopback(passphrase: str | None) -> list[str]:
    if passphrase is None:
        return []
    return ["--pinentry-mode", "loopback", "--passphrase", passphrase]


def generate(ctx: Ctx, uid: str, *, passphrase: str | None = None) -> str:
    """ed25519 cert/sign primary + cv25519 encryption subkey, no expiry. Returns the fpr.

    passphrase=None (production) -> gpg-agent asks via pinentry, so the call gets the tty.
    A string (tests only) -> loopback pinentry, no tty needed.
    """
    lb = _loopback(passphrase)
    tty = passphrase is None
    _must(
        _gpg(
            ctx, *lb, "--quick-gen-key", uid, "ed25519", "cert,sign", "never", interactive=tty
        ),
        f"gpg --quick-gen-key {uid!r}",
    )
    key = next((k for k in secret_keys(ctx) if uid in k.uids), None)
    if key is None:
        raise InstallError("pass-store", "gpg --list-secret-keys (new key not found)", 1)
    _must(
        _gpg(
            ctx, *lb, "--quick-add-key", key.fingerprint, "cv25519", "encr", "never",
            interactive=tty,
        ),
        f"gpg --quick-add-key {key.fingerprint}",
    )
    return key.fingerprint


def export_armored(ctx: Ctx, fp: str) -> str:
    res = _gpg(ctx, "--armor", "--export", fp)
    if not res.ok or "BEGIN PGP PUBLIC KEY BLOCK" not in res.stdout:
        raise InstallError("pass-store", f"gpg --armor --export {fp}", res.code or 1)
    return res.stdout


def import_trusted(ctx: Ctx, path: Path, fp: str) -> None:
    """Import a device public key and trust it ultimately (all keys are the user's own)."""
    _must(_gpg(ctx, "--import", str(path)), f"gpg --import {path}")
    _must(_gpg(ctx, "--import-ownertrust", stdin=f"{fp}:6:\n"), "gpg --import-ownertrust")
