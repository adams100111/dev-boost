"""age primitive — decrypt the provisioned secrets bundle via the `age` CLI (Executor).

JSON is parsed in-process with stdlib; the CLI is the only external dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from devboost.core.errors import SecretsError
from devboost.model import Ctx

REQUIRED_FIELDS = ("GIT_USER", "GIT_EMAIL", "GITHUB_PAT")

State = Literal["ok", "missing", "cannot-decrypt", "incomplete"]


def _decrypt_raw(ctx: Ctx, bundle: Path, key: Path) -> str | None:
    if not bundle.exists():
        return None
    res = ctx.ex.run(["age", "-d", "-i", str(key), str(bundle)])
    return res.stdout if res.ok else None


def decrypt(ctx: Ctx, bundle: Path, key: Path) -> dict[str, str]:
    """Decrypt the bundle to a JSON dict. Raises SecretsError on any failure."""
    if not bundle.exists():
        raise SecretsError(f"secrets bundle not found: {bundle}")
    raw = _decrypt_raw(ctx, bundle, key)
    if raw is None:
        raise SecretsError("cannot decrypt secrets bundle")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretsError("invalid JSON in decrypted bundle") from exc
    return {str(k): str(v) for k, v in data.items()}


def doctor_state(ctx: Ctx, bundle: Path, key: Path) -> State:
    """Probe the bundle without raising — returns one of four state tokens."""
    if not bundle.exists():
        return "missing"
    raw = _decrypt_raw(ctx, bundle, key)
    if raw is None:
        return "cannot-decrypt"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "cannot-decrypt"
    if any(not data.get(f) for f in REQUIRED_FIELDS):
        return "incomplete"
    return "ok"
