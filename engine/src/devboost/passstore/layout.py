"""The store's on-disk layout: .gpg-id files, entries, and the public `.devboost/` registry.

`.devboost/` holds only public keys and metadata — never secrets.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core import log
from devboost.core.errors import ConfigError

Kind = Literal["devices", "pending", "revoked"]


class DeviceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    fingerprint: str
    os: str
    enrolled_at: str | None = None
    requested_at: str | None = None
    scope: list[str] | None = None


class RotationEntry(BaseModel):
    device: str
    fingerprint: str
    revoked_at: str
    after: str
    entries: list[str]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.meta = root / ".devboost"

    def is_clone(self) -> bool:
        return (self.root / ".git").is_dir()

    def gpg_id_path(self, folder: str = "") -> Path:
        return (self.root / folder if folder else self.root) / ".gpg-id"

    def gpg_ids(self, folder: str = "") -> list[str]:
        p = self.gpg_id_path(folder)
        if not p.exists():
            return []
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def record_path(self, kind: Kind, name: str) -> Path:
        return self.meta / kind / f"{name}.json"

    def key_path(self, kind: Kind, name: str) -> Path:
        return self.meta / kind / f"{name}.asc"

    def record(self, kind: Kind, name: str) -> DeviceRecord | None:
        p = self.record_path(kind, name)
        if not p.exists():
            return None
        try:
            rec = DeviceRecord.model_validate_json(p.read_text(encoding="utf-8"))
        except (ValidationError, UnicodeDecodeError):
            log.warn(f"pass: ignoring malformed {p}")
            return None
        if rec.name != name or rec.name != p.stem:
            # Callers act on rec.name (approve / revoke / notices): it must be the file's name,
            # or a pushed `evil.json` could claim to be another device.
            log.warn(f"pass: ignoring {p} — it claims the name {rec.name!r}")
            return None
        return rec

    def records(self, kind: Kind) -> list[DeviceRecord]:
        d = self.meta / kind
        if not d.is_dir():
            return []
        out = [self.record(kind, p.stem) for p in sorted(d.glob("*.json"))]
        return [r for r in out if r is not None]

    def revoked_fingerprints(self) -> set[str]:
        """Fingerprints of every revoked device (upper-case): they never come back (I1)."""
        return {r.fingerprint.upper() for r in self.records("revoked")}

    def write_record(self, kind: Kind, rec: DeviceRecord, armored: str) -> None:
        path = self.record_path(kind, rec.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rec.model_dump_json(indent=2) + "\n", encoding="utf-8")
        self.key_path(kind, rec.name).write_text(armored, encoding="utf-8")

    def move(self, src: Kind, dst: Kind, name: str) -> None:
        (self.meta / dst).mkdir(parents=True, exist_ok=True)
        for s, d in ((self.record_path(src, name), self.record_path(dst, name)),
                     (self.key_path(src, name), self.key_path(dst, name))):
            if s.exists():
                s.replace(d)

    def rotation(self) -> list[RotationEntry]:
        p = self.meta / "rotation.json"
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("expected a JSON list")
            return [RotationEntry.model_validate(x) for x in raw]
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            raise ConfigError(f"pass: {p} is malformed ({exc.__class__.__name__}) — fix or "
                              "restore it from git history (`git log -p -- "
                              ".devboost/rotation.json`)") from exc

    def write_rotation(self, entries: Sequence[RotationEntry]) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        body = json.dumps([e.model_dump() for e in entries], indent=2) + "\n"
        (self.meta / "rotation.json").write_text(body, encoding="utf-8")

    def governing_folder(self, entry: str) -> str:
        """The folder whose `.gpg-id` pass encrypts *entry* to — the nearest one at or above
        the entry's folder (`""` = the root)."""
        parts = PurePosixPath(entry).parts[:-1]
        for i in range(len(parts), 0, -1):
            folder = "/".join(parts[:i])
            if self.gpg_id_path(folder).exists():
                return folder
        return ""

    def entries(self, folder: str = "") -> list[str]:
        base = self.root / folder if folder else self.root
        out: list[str] = []
        for p in base.rglob("*.gpg"):
            rel = p.relative_to(self.root)
            if rel.parts[0] in (".git", ".devboost"):
                continue
            out.append(rel.with_suffix("").as_posix())
        return sorted(out)
