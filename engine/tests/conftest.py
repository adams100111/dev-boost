from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from devboost.core import osinfo
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx

_REAL_DETECT = osinfo.detect


@pytest.fixture(autouse=True)
def _linux_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests are host-independent: an argument-less detect() sees Fedora on any machine.

    A call with any argument reaches the real detect(), with ``system`` defaulting to
    "Linux" so e.g. an ``os_release_path=`` fixture is really parsed, even on a Mac.
    """

    def _pinned(
        os_release_path: str | None = None,
        machine: str | None = None,
        env: Mapping[str, str] | None = None,
        default_target_link: str | None = None,
        system: str | None = None,
        mac_version: str | None = None,
    ) -> OsInfo:
        given: dict[str, Any] = {
            k: v
            for k, v in {
                "os_release_path": os_release_path,
                "machine": machine,
                "env": env,
                "default_target_link": default_target_link,
                "mac_version": mac_version,
            }.items()
            if v is not None
        }
        if not given and system is None:
            return OsInfo("fedora", "fedora", "x86_64", headless=False)
        return _REAL_DETECT(**given, system=system or "Linux")

    monkeypatch.setattr(osinfo, "detect", _pinned)


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
        'claude = ["claude-code"]\n'
        'codex = ["codex-code"]\n'
        'pi = ["pi-harness"]\n'
        'brain-host = ["mosh","caddy","crossarch-build","code-server","browser-view"]\n'
        'brain-tools = ["herdr","herdr-plugins"]\n'
        'omarchy = ["omarchy-update-hook"]\n'
        'orca = ["orca-ide"]\n'
        'orca-box = ["orca-ide","orca-serve"]\n'
        'macos = ["ripgrep"]\n',
        encoding="utf-8",
    )
    return p
