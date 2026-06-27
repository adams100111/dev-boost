"""Resolve bundled static data so paths work from source and inside the frozen binary."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """The directory holding bundled data (profiles.toml, templates/, …)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:  # running inside a PyInstaller one-file binary
        return Path(meipass)
    # running from source: the repo root (engine/src/devboost/exec/ -> repo root)
    return Path(__file__).resolve().parents[4]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def injection_archive_path(arch: str) -> Path:
    """Resolve the Ventoy injection tarball (``devboost-<arch>.tar.gz``).

    In **source** mode the tarball lives in ``dist/`` at the repo root (built by
    ``scripts/build-bundle.sh``).  In **frozen** mode (PyInstaller one-file binary) the
    tarball is shipped *alongside* the binary — not bundled inside ``_MEIPASS`` — so we
    look next to ``sys.executable`` instead.

    The release process ships ``devboost-<arch>`` + ``devboost-<arch>.tar.gz`` + checksums
    as a pair; this function finds the tarball regardless of whether it lives in the bundle
    directory or in the working tree.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        # Frozen: tarball is shipped alongside the binary, not inside _MEIPASS.
        # resolve() so a launch via the ~/.local/bin/devboost symlink (get.sh) still
        # finds the tarball next to the *real* binary in ~/.local/share/devboost/bin.
        return Path(sys.executable).resolve().parent / f"devboost-{arch}.tar.gz"
    # Source: in the repo's dist/ directory (created by scripts/build-bundle.sh).
    return resource_root() / "dist" / f"devboost-{arch}.tar.gz"
