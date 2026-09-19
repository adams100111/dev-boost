"""Config primitive: idempotent JSON merge + line-ensure, using stdlib for data."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.model import Ctx


def json_merge(ctx: Ctx, path: str, patch: Mapping[str, Any]) -> bool:
    """Idempotently merge `patch` into the JSON object at `path` (shallow, top-level keys).

    Returns True iff the file's contents changed.  When the target isn't writable in
    process (e.g. a root-owned file under /etc), the write is routed through the executor
    (`tee`, sudo) — mirroring `write_kv` — so privileged config is updated uniformly.
    """
    p = Path(path)
    current: dict[str, Any] = {}
    if p.exists():
        current = json.loads(p.read_text(encoding="utf-8"))
    merged = {**current, **patch}
    if merged == current:
        return False
    body = json.dumps(merged, indent=2) + "\n"
    # Writability is judged against the nearest EXISTING ancestor: a not-yet-created parent
    # under a writable dir (e.g. tmp/sub/) is still a direct write (we mkdir it), while a
    # root-owned tree (e.g. /etc/docker/) routes through the executor.
    probe = p if p.exists() else next(a for a in p.parents if a.exists())
    if os.access(probe, os.W_OK):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    else:
        ctx.ex.run(["tee", path], sudo=True, stdin=body)
    return True


def ensure_line(ctx: Ctx, path: str, line: str) -> None:
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if line not in lines:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join([*lines, line]) + "\n", encoding="utf-8")


def comment_block(text: str, begin: str, end: str) -> str:
    """Prefix '# ' to each non-empty, not-already-commented line within [begin, end]."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line == begin:
            inside = True
            out.append(line)
        elif line == end:
            inside = False
            out.append(line)
        elif inside and line and not line.startswith("# "):
            out.append(f"# {line}")
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def write_kv(ctx: Ctx, path: str, key: str, value: str) -> None:
    """Ensure `key=value` in an ini-style file (replace-not-append). Privileged via tee."""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out: list[str] = []
    replaced = False
    for ln in lines:
        if ln.split("=", 1)[0] == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"{key}={value}")
    body = "\n".join(out) + "\n"
    # Direct write when we can (existing writable file, or a writable parent dir);
    # otherwise route a privileged write through the executor.
    if p.exists():
        writable = os.access(path, os.W_OK)
    else:
        writable = os.access(p.parent, os.W_OK)
    if writable:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    else:
        ctx.ex.run(["tee", path], sudo=True, stdin=body)


# --- JSONC (Zed-style JSON with comments / trailing commas) ---------------------------------


def _skip_string(text: str, i: int, out: list[str]) -> int:
    """Copy the JSON string starting at text[i] == '"' into *out*; return the index after it."""
    out.append(text[i])
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        out.append(c)
        if c == "\\" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        i += 1
        if c == '"':
            break
    return i


def _drop_trailing_commas(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _skip_string(text, i, out)
            continue
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas, never touching strings.

    An unterminated block comment swallows the rest of the text, so the JSON parse that
    follows fails loudly instead of guessing.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _skip_string(text, i, out)
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(c)
            i += 1
    return _drop_trailing_commas("".join(out))


def deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Recursive merge: dicts recurse, any other patch value (lists included) wins.

    Keys only in *base* are always kept — this is how a user's own settings survive.
    """
    out: dict[str, Any] = dict(base)
    for key, value in patch.items():
        current = out.get(key)
        if isinstance(value, Mapping):
            out[key] = deep_merge(current if isinstance(current, Mapping) else {}, value)
        else:
            out[key] = value
    return out


def _parse_object(text: str) -> dict[str, Any]:
    data = json.loads(strip_jsonc(text))
    if not isinstance(data, dict):
        raise ValueError("top level is not a JSON object")
    return data


def _leaf_paths(patch: Mapping[str, Any], prefix: str = "") -> list[str]:
    out: list[str] = []
    for key, value in patch.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and value:
            out.extend(_leaf_paths(value, dotted))
        else:
            out.append(dotted)
    return out


def jsonc_satisfies(path: str, patch: Mapping[str, Any]) -> bool:
    """Pure check: does the JSONC file at *path* already contain every leaf of *patch*?"""
    p = Path(path)
    if not p.exists():
        return False
    try:
        current = _parse_object(p.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return deep_merge(current, patch) == current


def jsonc_merge_deep(ctx: Ctx, path: str, patch: Mapping[str, Any]) -> bool:
    """Guarantee *patch* inside a user-owned JSONC file (e.g. Zed's settings.json).

    No semantic change → no write (a commented file stays byte-identical). A needed change
    backs the original up to ``<file>.devboost-bak`` (unless a backup already exists and the
    raw bytes carry no comments/trailing commas — a plain-JSON rewrite must never clobber an
    earlier backup of the user's original commented file) and writes plain JSON atomically;
    comments are lost only then, and that is logged. A symlinked file is written through to
    its target (the link survives) and the file keeps its mode. An unparseable or
    undecodable file is never rewritten: the user gets ``NeedsUser`` with the exact keys.
    """
    p = Path(path)
    raw: str | None = None
    current: dict[str, Any] = {}
    try:
        if p.exists():
            raw = p.read_text(encoding="utf-8")
        if raw is not None and raw.strip():
            current = _parse_object(raw)
    except ValueError as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise NeedsUser(
            f"{path} is not valid UTF-8 JSON/JSONC ({exc})",
            "fix it (or delete it — dev-boost re-seeds a missing file) and re-run; "
            f"dev-boost must set: {', '.join(_leaf_paths(patch))}",
        ) from exc
    merged = deep_merge(current, patch)
    if raw is not None and merged == current:
        return False
    if raw is not None:
        backup = p.with_name(p.name + ".devboost-bak")
        has_comments = strip_jsonc(raw) != raw
        if not backup.exists() or has_comments:
            backup.write_text(raw, encoding="utf-8")
        if has_comments:
            log.warn(
                f"{path}: rewritten to add dev-boost keys — comments/trailing commas were "
                f"not preserved; the original is at {backup}"
            )
    _atomic_write(p, json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    return True


def _atomic_write(p: Path, body: str) -> None:
    """Replace *p* with *body* via a sibling temp file. A symlink is followed (its target is
    replaced, the link kept) and an existing file's permission bits are preserved."""
    target = p.resolve() if p.is_symlink() else p
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    tmp = target.with_name(target.name + ".devboost-tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        if mode is not None:
            tmp.chmod(mode)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
