"""The .NET SDK in ~/.dotnet and the Android SDK in ~/Library/Android/sdk on macOS."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.dev_stacks import AndroidSdk, DotnetSdk
from devboost.modules.macos import Homebrew
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PACKAGES = "'platform-tools' 'platforms;android-35' 'build-tools;35.0.0'"


def test_dotnet_on_macos_runs_the_official_script_into_home(tmp_path: Path) -> None:
    ex = Scripted(answers={("mktemp", "-d"): Result(0, stdout="/tmp/dn\n")})
    DotnetSdk().install(Ctx(os=MAC, ex=ex))
    assert ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o", "/tmp/dn/install.sh",
            "https://builds.dotnet.microsoft.com/dotnet/scripts/v1/dotnet-install.sh"] in ex.calls
    assert ["bash", "/tmp/dn/install.sh", "--channel", "10.0",
            "--install-dir", str(tmp_path / ".dotnet")] in ex.calls
    assert not any(c[0] == "sudo" for c in ex.calls)


@pytest.mark.parametrize(
    ("listing", "ok"), [("10.0.104 [/x/sdk]\n", True), ("9.0.300 [/x/sdk]\n", False)]
)
def test_dotnet_verify_reads_the_user_sdk(tmp_path: Path, listing: str, ok: bool) -> None:
    dotnet = str(tmp_path / ".dotnet" / "dotnet")
    ex = Scripted(answers={(dotnet, "--list-sdks"): Result(0, stdout=listing)})
    assert DotnetSdk().verify(Ctx(os=MAC, ex=ex)) is ok
    missing = Scripted(answers={(dotnet,): Result(127)})
    assert DotnetSdk().verify(Ctx(os=MAC, ex=missing)) is False


def test_dotnet_on_fedora_is_unchanged() -> None:
    ex = FakeExecutor()
    DotnetSdk().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "install", "-y", "dotnet-sdk-10.0"] in ex.calls


def test_android_on_macos_uses_the_cmdline_tools_cask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    ex = Scripted(answers={("brew", "list"): Result(1)})
    AndroidSdk().install(Ctx(os=MAC, ex=ex))
    sdk = tmp_path / "Library" / "Android" / "sdk"
    assert ex.calls[0] == ["mise", "use", "-g", "java@temurin-17"]
    assert ["brew", "install", "--cask", "-y", "--adopt", "android-commandlinetools"] in ex.calls
    assert ex.calls[-1] == ["sh", "-c", f"yes | sdkmanager --sdk_root={sdk} {PACKAGES}"]
    assert not any("profile.d" in " ".join(c) for c in ex.calls)
    assert sdk.is_dir()


def test_android_on_macos_install_twice_with_force_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-R17: an --update re-run (force=True) must not duplicate side effects or prompt."""
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    ex = Scripted(answers={("brew", "list"): Result(1)})
    ctx = Ctx(os=MAC, ex=ex, force=True)

    AndroidSdk().install(ctx)
    AndroidSdk().install(ctx)

    sdk = tmp_path / "Library" / "Android" / "sdk"
    cask_calls = [
        c for c in ex.calls
        if c[:2] == ["brew", "install"] and c[-1] == "android-commandlinetools"
    ]
    assert len(cask_calls) == 2  # brew's own install is idempotent, not skipped here
    assert all(c and c[0] != "sudo" for c in ex.calls)  # never prompts unattended
    assert sdk.is_dir()


def test_android_follows_android_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = tmp_path / "custom-sdk"
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    assert AndroidSdk().verify(Ctx(os=MAC, ex=FakeExecutor())) is False
    (sdk / "platform-tools").mkdir(parents=True)
    (sdk / "platform-tools" / "adb").write_text("", encoding="utf-8")
    assert AndroidSdk().verify(Ctx(os=MAC, ex=FakeExecutor())) is True


def test_android_requires_homebrew_on_a_mac() -> None:
    assert Homebrew in AndroidSdk.requires
