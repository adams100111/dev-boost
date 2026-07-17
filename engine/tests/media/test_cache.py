from __future__ import annotations

import hashlib
import time
from pathlib import Path

from devboost.media.cache import Cache


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_has_is_true_only_on_matching_checksum(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    name, data = "f44.iso", b"iso-bytes"
    p = cache.path_for(name, _sha(data))
    assert cache.has(name, _sha(data)) is False        # not present yet
    p.write_bytes(data)
    assert cache.has(name, _sha(data)) is True          # present + matches
    assert cache.has(name, _sha(b"other")) is False     # present but wrong checksum


def test_ttl_eviction_removes_stale_files(tmp_path: Path) -> None:
    cache = Cache(tmp_path, ttl_days=1)
    stale = tmp_path / "old.iso"
    stale.write_bytes(b"old")
    fresh = tmp_path / "new.iso"
    fresh.write_bytes(b"new")

    # Back-date the stale file to 2 days ago
    two_days_ago = time.time() - 2 * 86400
    import os
    os.utime(stale, (two_days_ago, two_days_ago))

    removed = cache.evict_stale()
    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()  # fresh file untouched


def test_ttl_eviction_noop_when_ttl_days_is_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path, ttl_days=None)
    f = tmp_path / "f.iso"
    f.write_bytes(b"data")
    # Back-date to 1000 days ago
    import os
    very_old = time.time() - 1000 * 86400
    os.utime(f, (very_old, very_old))
    assert cache.evict_stale() == 0
    assert f.exists()


def test_evict_stale_ignores_directories(tmp_path: Path) -> None:
    cache = Cache(tmp_path, ttl_days=1)
    sub = tmp_path / "subdir"
    sub.mkdir()
    # No files → nothing to evict
    assert cache.evict_stale() == 0
    assert sub.exists()


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    """One definition of "hashed" — Cache.verify and LocalIsoDownloader must agree."""
    import hashlib

    from devboost.media.cache import sha256_of

    blob = b"fedora" * 100_000  # spans several 1 MiB read chunks
    f = tmp_path / "x.iso"
    f.write_bytes(blob)
    assert sha256_of(f) == hashlib.sha256(blob).hexdigest()


def test_cache_verify_delegates_to_sha256_of(tmp_path: Path) -> None:
    """verify() must not keep a second copy of the loop."""
    import hashlib

    from devboost.media.cache import Cache

    f = tmp_path / "y.iso"
    f.write_bytes(b"payload")
    cache = Cache(tmp_path / "c")
    good = hashlib.sha256(b"payload").hexdigest()
    assert cache.verify(f, good) is True
    assert cache.verify(f, "b" * 64) is False
    assert cache.verify(tmp_path / "missing.iso", good) is False
