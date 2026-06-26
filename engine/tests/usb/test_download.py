from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from devboost.core.errors import DownloadError
from devboost.usb.cache import Cache
from devboost.usb.download import FakeDownloader


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_fake_downloader_writes_verifies_and_caches(tmp_path: Path) -> None:
    data = b"iso-bytes"
    dl = FakeDownloader(Cache(tmp_path), blobs={"https://x/f.iso": data})
    p = dl.fetch("https://x/f.iso", "f.iso", _sha(data))
    assert p.read_bytes() == data
    assert dl.fetched == ["https://x/f.iso"]
    # second fetch is served from cache (no re-download)
    p2 = dl.fetch("https://x/f.iso", "f.iso", _sha(data))
    assert p2 == p and dl.fetched == ["https://x/f.iso"]


def test_fake_downloader_rejects_bad_checksum(tmp_path: Path) -> None:
    dl = FakeDownloader(Cache(tmp_path), blobs={"https://x/f.iso": b"corrupt"})
    with pytest.raises(DownloadError):
        dl.fetch("https://x/f.iso", "f.iso", _sha(b"expected"))
