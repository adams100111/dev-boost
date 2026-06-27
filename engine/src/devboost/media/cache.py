"""Content-addressed cache for downloaded build artifacts (ISO, binary, Ventoy)."""

from __future__ import annotations

import hashlib
from pathlib import Path


class Cache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str, sha256: str) -> Path:
        return self.cache_dir / name

    def verify(self, path: Path, sha256: str) -> bool:
        if not path.exists():
            return False
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == sha256

    def has(self, name: str, sha256: str) -> bool:
        return self.verify(self.path_for(name, sha256), sha256)
