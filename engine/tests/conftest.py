from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx


@pytest.fixture
def fedora_os() -> OsInfo:
    return OsInfo(distro="fedora", family="fedora", arch="x86_64", headless=False)


@pytest.fixture
def ubuntu_os() -> OsInfo:
    return OsInfo(distro="ubuntu", family="debian", arch="x86_64", headless=False)


@pytest.fixture
def fake_ex() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
def fedora_ctx(fedora_os: OsInfo, fake_ex: FakeExecutor) -> Ctx:
    return Ctx(os=fedora_os, ex=fake_ex)


@pytest.fixture
def profiles_file(tmp_path: Path) -> Path:
    """A fixture profiles.toml referencing only the M0 tracer modules."""
    p = tmp_path / "profiles.toml"
    p.write_text(
        "[profiles]\n"
        'cli = ["ripgrep"]\n'
        'base = ["docker"]\n'
        'laravel = ["ddev"]\n'
        'full = ["cli", "base", "laravel"]\n'
        'terminal = ["ripgrep"]\n'
        'devtools = ["ddev"]\n',
        encoding="utf-8",
    )
    return p
