"""Ventoy bootstrap: download, verify, extract and locate ``Ventoy2Disk.sh``."""

from __future__ import annotations

import tarfile
from pathlib import Path

from devboost.core.errors import VentoyError
from devboost.media.cache import Cache
from devboost.media.catalog import ventoy_pin
from devboost.media.download import Downloader
from devboost.model import Ctx


def ensure_ventoy(ctx: Ctx, dl: Downloader, cache: Cache) -> Path:  # noqa: ARG001
    """Fetch + verify the pinned Ventoy tarball, extract it, and return the path to
    ``Ventoy2Disk.sh``.

    On repeated calls the cached tarball is used; extraction is skipped when the script
    already exists on disk.  ``ctx`` is accepted for API symmetry (future: could be used
    to run extraction via the Executor).
    """
    pin = ventoy_pin()
    tarball_name = f"ventoy-{pin.version}-linux.tar.gz"
    tarball = dl.fetch(pin.url, tarball_name, pin.sha256)

    # The tarball extracts to ventoy-<version>/ (e.g. ventoy-1.1.16/).
    extract_root = cache.cache_dir / f"ventoy-{pin.version}"
    script = extract_root / f"ventoy-{pin.version}" / "Ventoy2Disk.sh"

    if not script.exists():
        extract_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as tf:
            tf.extractall(extract_root, filter="data")

    if not script.exists():
        raise VentoyError(
            f"Ventoy2Disk.sh not found after extraction (expected {script}); "
            "tarball structure may have changed — check the [ventoy] pin in catalog.toml"
        )
    return script
