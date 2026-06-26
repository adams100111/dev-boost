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
