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


# --- LocalIsoDownloader: serve a user-supplied ISO instead of downloading it ---------------


def _local(tmp_path: Path, blob: bytes = b"a pretend fedora iso") -> tuple[Path, str]:
    import hashlib

    p = tmp_path / "my-fedora.iso"
    p.write_bytes(blob)
    return p, hashlib.sha256(blob).hexdigest()


def test_local_iso_downloader_serves_the_matching_name_in_place(tmp_path: Path) -> None:
    """The user's file is used where it lies — never copied into the cache, where
    evict_stale() could later delete it."""
    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    local, sha = _local(tmp_path)
    cache = Cache(tmp_path / "cache")
    inner = FakeDownloader(cache, blobs={})
    dl = LocalIsoDownloader(inner, "fedora-44.iso", local, sha)
    dl.check()

    assert dl.fetch("https://x/f.iso", "fedora-44.iso", sha) == local
    assert inner.fetched == []                                    # nothing downloaded
    assert not (cache.cache_dir / "fedora-44.iso").exists()       # not copied into the cache


def test_local_iso_downloader_delegates_every_other_artifact(tmp_path: Path) -> None:
    """--iso-path is the primary ISO only: netinst and the Ventoy tarball still download."""
    import hashlib

    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    local, sha = _local(tmp_path)
    netinst = b"netinst bytes"
    cache = Cache(tmp_path / "cache")
    inner = FakeDownloader(cache, blobs={"https://x/n.iso": netinst})

    dl = LocalIsoDownloader(inner, "fedora-44.iso", local, sha)
    out = dl.fetch("https://x/n.iso", "fedora-44-netinst.iso", hashlib.sha256(netinst).hexdigest())
    assert out.read_bytes() == netinst
    assert inner.fetched == ["https://x/n.iso"]


def test_local_iso_downloader_check_rejects_a_mismatched_iso(tmp_path: Path) -> None:
    """A file that is not the pinned release must stop the build, naming both hashes."""
    import hashlib

    import pytest

    from devboost.core.errors import MediaError
    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    local = tmp_path / "wrong.iso"
    local.write_bytes(b"some other release")
    actual = hashlib.sha256(b"some other release").hexdigest()
    pinned = "1" * 64

    dl = LocalIsoDownloader(
        FakeDownloader(Cache(tmp_path / "c"), blobs={}), "fedora-44.iso", local, pinned
    )
    with pytest.raises(MediaError) as exc:
        dl.check()
    msg = str(exc.value)
    assert str(local) in msg and pinned in msg and actual in msg and "catalog.toml" in msg


def test_local_iso_downloader_check_rejects_a_missing_file(tmp_path: Path) -> None:
    import pytest

    from devboost.core.errors import MediaError
    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    dl = LocalIsoDownloader(
        FakeDownloader(Cache(tmp_path / "c"), blobs={}),
        "fedora-44.iso", tmp_path / "nope.iso", "a" * 64,
    )
    with pytest.raises(MediaError, match="nope.iso"):
        dl.check()


def test_local_iso_downloader_fetch_does_not_rehash_after_check(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """check() hashes multiple GB; fetch() must not do it again."""
    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    local, sha = _local(tmp_path)
    dl = LocalIsoDownloader(
        FakeDownloader(Cache(tmp_path / "c"), blobs={}), "fedora-44.iso", local, sha
    )
    dl.check()  # the one and only hash

    calls = {"n": 0}

    def counting(path: Path) -> str:
        calls["n"] += 1
        return "deadbeef"

    monkeypatch.setattr("devboost.media.download.sha256_of", counting)
    assert dl.fetch("https://x/f.iso", "fedora-44.iso", sha) == local
    assert calls["n"] == 0


def test_local_iso_downloader_refuses_a_different_pin_for_the_same_name(tmp_path: Path) -> None:
    """Guards a future caller asking for a different pin under the same filename: it must
    fail loudly, not silently receive a file verified against something else."""
    import pytest

    from devboost.core.errors import MediaError
    from devboost.media.cache import Cache
    from devboost.media.download import FakeDownloader, LocalIsoDownloader

    local, sha = _local(tmp_path)
    dl = LocalIsoDownloader(
        FakeDownloader(Cache(tmp_path / "c"), blobs={}), "fedora-44.iso", local, sha
    )
    dl.check()
    with pytest.raises(MediaError, match="different sha256"):
        dl.fetch("https://x/f.iso", "fedora-44.iso", "9" * 64)
