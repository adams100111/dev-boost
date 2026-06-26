from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.usb.cache import Cache


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
