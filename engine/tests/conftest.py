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
    # Must declare every profile the registered catalog references (load-time validation
    # checks each module's `profiles` against these keys). Members only need to resolve
    # for profiles actually exercised by a test.
    p.write_text(
        "[profiles]\n"
        'cli = ["ripgrep"]\n'
        'base = ["docker"]\n'
        'shell = ["starship"]\n'
        'gnome = ["gnome-settings"]\n'
        'gnome-theme = ["gnome-theme-bundle"]\n'
        'gnome-aesthetics = ["gnome-aesthetics-bundle"]\n'
        'multimedia = ["openh264"]\n'
        'editors = ["fresh"]\n'
        'python = ["uv"]\n'
        'web = ["web-runtimes"]\n'
        'dotnet = ["dotnet-sdk"]\n'
        'data = ["data-services"]\n'
        'devops = ["devops-tools"]\n'
        'react-native = ["expo"]\n'
        'apps = ["obsidian"]\n'
        'dev-hygiene = ["aspire-gc"]\n'
        'system = ["gpu-detect"]\n'
        'hardware-nvidia = ["nvidia-akmod"]\n'
        'optional-editors = ["neovim"]\n'
        'security-cli = ["pass"]\n'
        'optional-agents = ["herdr"]\n'
        'laravel = ["ddev"]\n'
        'full = ["cli", "base", "laravel"]\n'
        'terminal = ["ripgrep"]\n'
        'devtools = ["ddev"]\n'
        'server = ["zram"]\n'
        'remote = ["tailscale","mosh"]\n'
        'brain-host = ["mosh","caddy"]\n',
        encoding="utf-8",
    )
    return p
