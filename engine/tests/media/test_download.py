from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from devboost.core.errors import DownloadError
from devboost.media.cache import Cache
from devboost.media.download import FakeDownloader


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


def test_urllib_downloader_drives_progress_with_byte_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from devboost.media.cache import Cache
    from devboost.media.download import UrllibDownloader
    from devboost.media.report import FakeReporter

    data = b"x" * 2500
    sha = _sha(data)

    class _Resp(io.BytesIO):
        headers = {"Content-Length": str(len(data))}

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: object) -> None:
            self.close()

    monkeypatch.setattr(
        "devboost.media.download.urllib.request.urlopen", lambda url: _Resp(data)
    )
    reporter = FakeReporter()
    dl = UrllibDownloader(Cache(tmp_path), reporter)
    out = dl.fetch("https://x/f.iso", "f.iso", sha)
    assert out.read_bytes() == data
    assert reporter.progress_calls == [("f.iso", len(data))]
    assert sum(reporter.advances) == len(data)


def test_urllib_downloader_drives_indeterminate_progress_when_no_content_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Content-Length is absent, progress is called with total=0 (indeterminate)."""
    import io

    from devboost.media.cache import Cache
    from devboost.media.download import UrllibDownloader
    from devboost.media.report import FakeReporter

    data = b"small"
    sha = _sha(data)

    class _RespNoLen(io.BytesIO):
        headers: dict[str, str] = {}  # no Content-Length header

        def __enter__(self) -> _RespNoLen:
            return self

        def __exit__(self, *a: object) -> None:
            self.close()

    monkeypatch.setattr(
        "devboost.media.download.urllib.request.urlopen", lambda url: _RespNoLen(data)
    )
    reporter = FakeReporter()
    dl = UrllibDownloader(Cache(tmp_path), reporter)
    out = dl.fetch("https://x/f.iso", "f.iso", sha)
    assert out.read_bytes() == data
    # progress was called with total=0 (indeterminate), not skipped entirely
    assert reporter.progress_calls == [("f.iso", 0)]


def test_urllib_downloader_cleans_part_file_on_network_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.part file must not be left on disk after a network error."""
    from devboost.media.cache import Cache
    from devboost.media.download import UrllibDownloader

    def _raise(url: object) -> None:
        raise OSError("connection reset")

    monkeypatch.setattr("devboost.media.download.urllib.request.urlopen", _raise)
    dl = UrllibDownloader(Cache(tmp_path))
    with pytest.raises(DownloadError):
        dl.fetch("https://x/f.iso", "f.iso", _sha(b"x"))

    # No .part files should remain
    part_files = list(tmp_path.glob("*.part"))
    assert part_files == [], f"leaked .part files: {part_files}"


def test_urllib_downloader_cleans_part_file_on_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """.part file must not persist after a checksum failure."""
    import io

    from devboost.media.cache import Cache
    from devboost.media.download import UrllibDownloader

    data = b"corrupt"

    class _Resp(io.BytesIO):
        headers: dict[str, str] = {}

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *a: object) -> None:
            self.close()

    monkeypatch.setattr(
        "devboost.media.download.urllib.request.urlopen", lambda url: _Resp(data)
    )
    dl = UrllibDownloader(Cache(tmp_path))
    with pytest.raises(DownloadError, match="checksum"):
        dl.fetch("https://x/f.iso", "f.iso", _sha(b"expected-different"))

    part_files = list(tmp_path.glob("*.part"))
    assert part_files == [], f"leaked .part files after checksum failure: {part_files}"
