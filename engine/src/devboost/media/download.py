"""Download seam: cache-hit-or-fetch-and-verify. Real impl uses stdlib urllib."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from devboost.core.errors import DownloadError, MediaError
from devboost.media.cache import Cache, sha256_of
from devboost.media.report import Reporter


@runtime_checkable
class Downloader(Protocol):
    def fetch(self, url: str, name: str, sha256: str) -> Path: ...


class UrllibDownloader:
    def __init__(self, cache: Cache, reporter: Reporter | None = None) -> None:
        self.cache = cache
        self.reporter = reporter

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            try:
                with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
                    # total=0 when Content-Length is absent; progress bar runs indeterminate.
                    total = int(resp.headers.get("Content-Length", 0) or 0)
                    if self.reporter is not None:
                        with self.reporter.progress(name, total) as advance:
                            for chunk in iter(lambda: resp.read(1 << 20), b""):
                                out.write(chunk)
                                advance(len(chunk))
                    else:
                        shutil.copyfileobj(resp, out)
            except OSError as exc:
                raise DownloadError(url, str(exc)) from exc
            if not self.cache.verify(tmp, sha256):
                raise DownloadError(url, "checksum mismatch")
            tmp.replace(dest)
        except Exception:
            # Always remove the .part file on any failure so we never leave disk-eating debris.
            tmp.unlink(missing_ok=True)
            raise
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


class LocalIsoDownloader:
    """Serves one user-supplied ISO from disk; delegates every other artifact to *inner*.

    The user's file is used **in place** — never copied into the cache, so
    ``Cache.evict_stale()`` can never delete it.

    ``check()`` is separate because the primary ISO is fetched from inside ``_mounted_vtoy``,
    i.e. *after* the stick is wiped and Ventoy installed. Verifying only at fetch time would
    destroy the stick and then reject the ISO, so callers must call ``check()`` before
    anything destructive. It is memoised: hashing multiple GB once is enough.
    """

    def __init__(self, inner: Downloader, name: str, path: Path, sha256: str) -> None:
        self._inner = inner
        self._name = name
        self._path = path
        self._sha256 = sha256
        self._checked = False

    def check(self) -> None:
        """Verify the local ISO against the catalog pin, or raise MediaError."""
        if not self._path.is_file():
            raise MediaError(f"--iso-path {self._path}: not a readable file")
        try:
            actual = sha256_of(self._path)
        except OSError as exc:
            raise MediaError(f"--iso-path {self._path}: cannot read ({exc.strerror})") from exc
        if actual != self._sha256:
            raise MediaError(
                f"{self._path} does not match the pinned {self._name.removesuffix('.iso')} ISO\n"
                f"  expected {self._sha256}  (catalog.toml)\n"
                f"  got      {actual}\n"
                "This is a different release or a corrupt file. "
                "Omit --iso-path to fetch the pinned ISO."
            )
        self._checked = True

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        if name != self._name:
            return self._inner.fetch(url, name, sha256)
        if sha256 != self._sha256:
            raise MediaError(
                f"{name} was requested with a different sha256 than --iso-path was verified "
                f"against (verified {self._sha256}, requested {sha256})"
            )
        if not self._checked:
            self.check()
        return self._path
