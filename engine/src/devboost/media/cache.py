"""Download cache for build artifacts (ISOs, Ventoy tarball, frozen binary).

Caching is **opt-in**: ``--cache-dir`` or the wizard's cache prompt persist downloads across
runs; only ``--device`` without ``--cache-dir`` uses an ephemeral temp dir, cleaned up
after the build. An optional TTL (``ttl_days``) evicts files older than N days.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path


def sha256_of(path: Path) -> str:
    """The lowercase hex sha256 of *path*, streamed so a multi-GB ISO costs no memory.

    The single definition of "hashed" for the media pipeline: the download cache and the
    local-ISO downloader must agree byte-for-byte on what verification means. Two copies of
    that is the shape of bugs this codebase has already shipped twice.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Cache:
    def __init__(self, cache_dir: Path, *, ttl_days: int | None = None) -> None:
        self.cache_dir = cache_dir
        self.ttl_days = ttl_days
        cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str, sha256: str) -> Path:  # noqa: ARG002
        return self.cache_dir / name

    def verify(self, path: Path, sha256: str) -> bool:
        if not path.exists():
            return False
        return sha256_of(path) == sha256

    def has(self, name: str, sha256: str) -> bool:
        return self.verify(self.path_for(name, sha256), sha256)

    def evict_stale(self) -> int:
        """Remove regular files older than ``ttl_days``.  Returns the number of files removed.

        No-op when ``ttl_days`` is ``None``.
        """
        if self.ttl_days is None:
            return 0
        cutoff = time.time() - self.ttl_days * 86400
        removed = 0
        for entry in self.cache_dir.iterdir():
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink(missing_ok=True)
                removed += 1
        return removed
