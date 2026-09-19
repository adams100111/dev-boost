from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import android_emulator as emu

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")


@pytest.fixture(autouse=True)
def _no_sdk_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real ANDROID_HOME / ANDROID_AVD_HOME leak into a test."""
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_AVD_HOME", raising=False)


def test_image_abi_follows_the_host() -> None:
    assert emu.system_image(MAC) == "system-images;android-35;google_apis;arm64-v8a"
    assert emu.system_image(FEDORA) == "system-images;android-35;google_apis;x86_64"


def test_sdk_root_defaults_per_os(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert emu.sdk_root(MAC) == tmp_path / "Library" / "Android" / "sdk"
    assert emu.sdk_root(FEDORA) == tmp_path / "Android" / "Sdk"
    monkeypatch.setenv("ANDROID_HOME", "/opt/sdk")
    assert emu.sdk_root(MAC) == Path("/opt/sdk")


def test_no_linux_arm64_emulator_host() -> None:
    assert emu.AndroidEmulator.supported_on(MAC) is True
    assert emu.AndroidEmulator.supported_on(FEDORA) is True
    assert emu.AndroidEmulator.supported_on(FEDORA_ARM) is False


def test_install_fetches_emulator_and_image_then_creates_the_avd(tmp_path: Path) -> None:
    ex = FakeExecutor()
    emu.AndroidEmulator().install(Ctx(os=MAC, ex=ex))
    root = tmp_path / "Library" / "Android" / "sdk"
    sdkm = ex.calls[0]
    assert sdkm[:2] == ["sh", "-c"]
    assert f"--sdk_root={root}" in sdkm[2]
    assert "emulator 'system-images;android-35;google_apis;arm64-v8a'" in sdkm[2]
    assert ex.calls[1] == [
        "avdmanager", "create", "avd", "-n", "devboost-pixel",
        "-k", "system-images;android-35;google_apis;arm64-v8a", "-d", "pixel_8",
    ]


def test_existing_avd_is_kept(tmp_path: Path) -> None:
    emu.avd_ini().parent.mkdir(parents=True)
    emu.avd_ini().touch()
    ex = FakeExecutor()
    emu.AndroidEmulator().install(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[:1] == ["avdmanager"]]


def test_verify_needs_emulator_image_and_avd() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert emu.AndroidEmulator().verify(ctx) is False
    root = emu.sdk_root(MAC)
    (root / "emulator").mkdir(parents=True)
    (root / "emulator" / "emulator").touch()
    (root / "system-images" / "android-35" / "google_apis" / "arm64-v8a").mkdir(parents=True)
    emu.avd_ini().parent.mkdir(parents=True)
    emu.avd_ini().touch()
    assert emu.AndroidEmulator().verify(ctx) is True
