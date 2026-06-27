"""Tests for the Ventoy bootstrap helper (ensure_ventoy)."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.media.cache import Cache
from devboost.media.download import FakeDownloader
from devboost.media.ventoy import ensure_ventoy
from devboost.model import Ctx

OS = OsInfo("fedora", "fedora", "x86_64")

# Matches the pin in catalog.toml / ventoy_pin()
_VENTOY_VERSION = "1.1.16"
_VENTOY_URL = (
    f"https://github.com/ventoy/Ventoy/releases/download/"
    f"v{_VENTOY_VERSION}/ventoy-{_VENTOY_VERSION}-linux.tar.gz"
)


def _make_ventoy_tarball(version: str) -> bytes:
    """Build a minimal in-memory .tar.gz that mimics the real Ventoy tarball structure."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        script_content = b"#!/bin/sh\necho Ventoy2Disk\n"
        info = tarfile.TarInfo(name=f"ventoy-{version}/Ventoy2Disk.sh")
        info.size = len(script_content)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(script_content))
        # Add a dummy extra file to make it more realistic
        dummy = b"dummy"
        info2 = tarfile.TarInfo(name=f"ventoy-{version}/ventoy.sh")
        info2.size = len(dummy)
        tf.addfile(info2, io.BytesIO(dummy))
    return buf.getvalue()


def test_ensure_ventoy_returns_path_to_ventoy2disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_ventoy should fetch the tarball, extract it, and return Ventoy2Disk.sh path."""
    tarball_bytes = _make_ventoy_tarball(_VENTOY_VERSION)
    sha = hashlib.sha256(tarball_bytes).hexdigest()

    # Monkeypatch ventoy_pin() to return a spec with our fake sha256
    from devboost.media.catalog import VentoySpec

    pin = VentoySpec(version=_VENTOY_VERSION, url=_VENTOY_URL, sha256=sha)
    monkeypatch.setattr("devboost.media.ventoy.ventoy_pin", lambda: pin)

    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={_VENTOY_URL: tarball_bytes})
    ctx = Ctx(os=OS, ex=FakeExecutor())

    script = ensure_ventoy(ctx, dl, cache)
    assert script.name == "Ventoy2Disk.sh"
    assert script.exists()
    assert script.stat().st_size > 0


def test_ensure_ventoy_skips_extraction_when_script_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If Ventoy2Disk.sh already exists, the tarball is fetched but extraction is skipped."""
    tarball_bytes = _make_ventoy_tarball(_VENTOY_VERSION)
    sha = hashlib.sha256(tarball_bytes).hexdigest()

    from devboost.media.catalog import VentoySpec

    pin = VentoySpec(version=_VENTOY_VERSION, url=_VENTOY_URL, sha256=sha)
    monkeypatch.setattr("devboost.media.ventoy.ventoy_pin", lambda: pin)

    cache = Cache(tmp_path / "cache")
    # Pre-create the expected script location so extraction is skipped
    script_dir = cache.cache_dir / f"ventoy-{_VENTOY_VERSION}" / f"ventoy-{_VENTOY_VERSION}"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "Ventoy2Disk.sh"
    script_path.write_text("#!/bin/sh\n", encoding="utf-8")

    dl = FakeDownloader(cache, blobs={_VENTOY_URL: tarball_bytes})
    ctx = Ctx(os=OS, ex=FakeExecutor())

    result = ensure_ventoy(ctx, dl, cache)
    assert result == script_path
    # The tarball was fetched (normal dl.fetch cache hit/miss logic)
    # but the script was not re-extracted (no tarfile errors even though blob is valid)


def test_ensure_ventoy_raises_if_script_missing_after_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If Ventoy2Disk.sh is absent after extraction, VentoyError is raised."""
    from devboost.core.errors import VentoyError

    # Tarball with wrong internal structure (no Ventoy2Disk.sh at expected path)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="wrong-structure/something.sh")
        data = b"#!/bin/sh\n"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    bad_tarball = buf.getvalue()
    sha = hashlib.sha256(bad_tarball).hexdigest()

    from devboost.media.catalog import VentoySpec

    pin = VentoySpec(version=_VENTOY_VERSION, url=_VENTOY_URL, sha256=sha)
    monkeypatch.setattr("devboost.media.ventoy.ventoy_pin", lambda: pin)

    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={_VENTOY_URL: bad_tarball})
    ctx = Ctx(os=OS, ex=FakeExecutor())

    with pytest.raises(VentoyError, match="Ventoy2Disk.sh not found"):
        ensure_ventoy(ctx, dl, cache)
