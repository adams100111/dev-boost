"""Download seam: cache-hit-or-fetch-and-verify. Real impl uses stdlib urllib."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from devboost.core.errors import DownloadError
from devboost.usb.cache import Cache


@runtime_checkable
class Downloader(Protocol):
    def fetch(self, url: str, name: str, sha256: str) -> Path: ...


class UrllibDownloader:
    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            raise DownloadError(url, str(exc)) from exc
        if not self.cache.verify(tmp, sha256):
            tmp.unlink(missing_ok=True)
            raise DownloadError(url, "checksum mismatch")
        tmp.replace(dest)
        return dest


class FakeDownloader:
    def __init__(self, cache: Cache, blobs: dict[str, bytes]) -> None:
        self.cache = cache
        self.blobs = blobs
        self.fetched: list[str] = []

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        self.fetched.append(url)
        dest.write_bytes(self.blobs[url])
        if not self.cache.verify(dest, sha256):
            dest.unlink(missing_ok=True)
            raise DownloadError(url, "checksum mismatch")
        return dest
