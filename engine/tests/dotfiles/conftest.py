"""Fixtures for dotfile tests: fake binaries, a HOME with the shell fragments, and
hermetic chezmoi render/apply of the real source for a chosen OS (no real $HOME touched)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

DOT = Path(__file__).resolve().parents[3] / "dotfiles"
FRAGMENTS = DOT / "dot_config" / "devboost"
CHEZMOI = shutil.which("chezmoi")

MakeBin = Callable[[str, str], Path]
Render = Callable[[Path, str, str], str]
Apply = Callable[[str, str], Path]


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    return d


@pytest.fixture
def make_bin(bin_dir: Path) -> MakeBin:
    """Write an executable ``#!/bin/sh`` fake named *name* into ``bin_dir``."""

    def make(name: str, body: str) -> Path:
        p = bin_dir / name
        p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        p.chmod(0o755)
        return p

    return make


@pytest.fixture
def frag_home(tmp_path: Path) -> Path:
    """A HOME with dev-boost's shell fragments where the rc files look for them."""
    home = tmp_path / "home"
    dest = home / ".config" / "devboost"
    dest.mkdir(parents=True)
    for f in FRAGMENTS.iterdir():
        if f.is_file():
            shutil.copy(f, dest / f.name)
    return home


def _data(os_name: str, distro: str) -> str:
    return json.dumps({"chezmoi": {"os": os_name, "osRelease": {"id": distro}}})


@pytest.fixture
def chezmoi_render(tmp_path: Path) -> Render:
    """Render one source template as chezmoi would on *os_name* / *distro*."""
    if CHEZMOI is None:
        pytest.skip("chezmoi not installed")
    exe = CHEZMOI

    def render(template: Path, os_name: str, distro: str) -> str:
        res = subprocess.run(
            [exe, "execute-template", "--source", str(DOT),
             "--config", str(tmp_path / "chezmoi.toml"),
             "--override-data", _data(os_name, distro)],
            input=template.read_text(encoding="utf-8"),
            capture_output=True, text=True, check=True,
        )
        return res.stdout

    return render


@pytest.fixture
def chezmoi_apply(tmp_path: Path) -> Apply:
    """Apply the whole source into a fresh HOME as chezmoi would on *os_name*/*distro*."""
    if CHEZMOI is None:
        pytest.skip("chezmoi not installed")
    exe = CHEZMOI

    def apply(os_name: str, distro: str) -> Path:
        tag = f"{os_name}-{distro}"
        home = tmp_path / f"home-{tag}"
        home.mkdir()
        subprocess.run(
            [exe, "apply", "--force", "--no-tty", "--source", str(DOT),
             "--destination", str(home), "--config", str(tmp_path / "chezmoi.toml"),
             "--persistent-state", str(tmp_path / f"{tag}.boltdb"),
             "--cache", str(tmp_path / f"cache-{tag}"),
             "--override-data", _data(os_name, distro)],
            env={**os.environ, "HOME": str(home)},
            capture_output=True, text=True, check=True,
        )
        return home

    return apply
