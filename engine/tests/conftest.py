from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from devboost.core import osinfo
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import default_apps, launchd
from devboost.model import Ctx

_REAL_DETECT = osinfo.detect


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test sees the developer's real home: HOME and the XDG base dirs point into
    ``tmp_path`` (laid out as their defaults under that HOME). A test that sets its own
    HOME still wins — its monkeypatch runs after this one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local" / "share"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".local" / "state"))
    monkeypatch.delenv("MISE_DATA_DIR", raising=False)
    monkeypatch.delenv("DEVBOOST_DOCKER_RUNTIME", raising=False)
    monkeypatch.delenv("GNUPGHOME", raising=False)
    monkeypatch.delenv("PASSWORD_STORE_GPG_OPTS", raising=False)
    # No test writes (or reads) the host's real /Library/LaunchDaemons — a test that runs
    # a root LaunchDaemon strategy (docker's Colima socket daemon, `system_daemon`,
    # `remove_daemon`) without its own redirect would otherwise depend on what this Mac
    # has installed there (M4-D handoff).
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")


#: Every ``/Applications/*.app`` bundle a module probes for, as (module, attribute).
#: ``tests/core/test_macos_contract.py`` fails if src grows one that is not listed here.
HOST_APP_PATHS: tuple[tuple[str, str], ...] = (
    ("devboost.modules.server", "_TS_APP"),
    ("devboost.modules.editors", "_ZED_APP"),
    ("devboost.modules.voxtype", "APP_BUNDLE"),
    ("devboost.modules._docker_orbstack", "APP"),
    ("devboost.modules._docker_desktop", "APP"),
)


@pytest.fixture(autouse=True)
def _no_host_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test sees the host's real /Applications: every app-bundle constant points at a
    path that does not exist. A test that needs the app present creates a bundle under
    tmp_path and monkeypatches the constant to it (its monkeypatch runs after this one)."""
    for name, attr in HOST_APP_PATHS:
        module = importlib.import_module(name)
        absent = tmp_path / "absent-apps" / getattr(module, attr).name
        monkeypatch.setattr(module, attr, absent)


@pytest.fixture(autouse=True)
def _no_deferred_default_apps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test is a fresh process for default_apps: no deferral leaks between tests."""
    monkeypatch.setattr(default_apps, "_deferred", {})


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
        'optional-terminals = ["wezterm"]\n'
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
        'macos = ["ripgrep"]\n'
        'macos-desktop = ["macos-defaults"]\n'
        'ios = ["xcode"]\n'
        'macos-extras = ["maccy"]\n',
        encoding="utf-8",
    )
    return p
