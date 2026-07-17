"""Ubuntu/Debian path tests for dev-stacks modules.

Every test runs against OsInfo(distro="ubuntu", family="debian") to prove that
install paths resolve the correct packages, repos, and commands on Ubuntu (24.04).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.dev_stacks import (
    AndroidSdk,
    Aspire,
    DataServices,
    DevopsTools,
    DotnetLsp,
    DotnetSdk,
    Expo,
    LaravelLsp,
    Uv,
    WebRuntimes,
)

UBUNTU = OsInfo(
    distro="ubuntu", family="debian", arch="x86_64",
    version_id="24.04", codename="noble",
)


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# python/uv — curl-installed, cross-distro
# ---------------------------------------------------------------------------


def test_uv_uses_curl_installer_on_ubuntu() -> None:
    ctx = _ctx()
    Uv().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("astral.sh/uv" in " ".join(c) for c in calls)
    assert not any("apt-get" in " ".join(c) for c in calls)


def test_uv_verify_checks_which_on_ubuntu() -> None:
    ctx_absent = _ctx()
    assert Uv().verify(ctx_absent) is False
    ctx_present = _ctx(present={"uv"})
    assert Uv().verify(ctx_present) is True


# ---------------------------------------------------------------------------
# web/node — mise-based, cross-distro
# ---------------------------------------------------------------------------


def test_web_runtimes_uses_mise_on_ubuntu() -> None:
    ctx = _ctx()
    WebRuntimes().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["mise", "use", "-g", "node@22", "pnpm@11.8.0", "bun@1.3.14"] in calls
    assert not any("apt-get" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# laravel/ddev — LSP install is mise-based; Ddev apt repo tested separately
# ---------------------------------------------------------------------------


def test_laravel_lsp_install_runs_mise_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    LaravelLsp().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("mise" in " ".join(c) for c in calls)


def test_ddev_adds_apt_repo_on_ubuntu() -> None:
    """ddev installs from its official apt repo on Ubuntu (not the Fedora yum repo)."""
    from devboost.modules.ddev import Ddev

    ctx = _ctx()
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # The apt repo sources file must be written
    assert any("sources.list.d" in " ".join(c) for c in calls)
    # The repo URL is ddev's apt repo
    assert any("pkg.ddev.com" in " ".join(c) for c in calls)
    # The ddev package is installed via apt-get
    assert ["sudo", "apt-get", "install", "-y", "ddev"] in calls
    # Fedora yum-specific steps must not appear
    assert not any("yum.repos.d" in " ".join(c) for c in calls)
    assert not any("dnf" in " ".join(c) for c in calls)


def test_ddev_still_installs_mkcert_and_runs_it_on_ubuntu() -> None:
    from devboost.modules.ddev import Ddev

    ctx = _ctx()
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "mkcert"] in calls
    assert ["mkcert", "-install"] in calls


def test_ddev_skips_mkcert_pkg_when_already_present_on_ubuntu() -> None:
    from devboost.modules.ddev import Ddev

    ctx = _ctx(present={"mkcert"})
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any(c == ["sudo", "apt-get", "install", "-y", "mkcert"] for c in calls)
    assert ["mkcert", "-install"] in calls


# ---------------------------------------------------------------------------
# dotnet — Microsoft APT repo added on Ubuntu; aspire/lsp are dotnet tools
# ---------------------------------------------------------------------------


def test_dotnet_sdk_uses_microsoft_config_deb_on_ubuntu() -> None:
    """.NET on Ubuntu installs via Microsoft's official config package, which wires
    up the correct prod repo AND its current signing key for the running release —
    not a hand-rolled repo line + the generic microsoft.asc (which misses the key)."""
    ctx = _ctx()
    DotnetSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    blob = " ".join(" ".join(c) for c in calls)
    # version-matched config package fetched + installed
    assert "config/ubuntu/24.04/packages-microsoft-prod.deb" in blob
    assert ["sudo", "dpkg", "-i", "/tmp/packages-microsoft-prod.deb"] in calls
    assert ["sudo", "apt-get", "update"] in calls
    assert ["sudo", "apt-get", "install", "-y", "dotnet-sdk-10.0"] in calls
    # the broken hand-rolled path must be gone
    assert "microsoft.asc" not in blob
    assert "/prod noble main" not in blob


def test_dotnet_sdk_installs_via_apt_on_ubuntu() -> None:
    ctx = _ctx()
    DotnetSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "dotnet-sdk-10.0"] in calls
    assert not any("dnf" in " ".join(c) for c in calls)


def test_dotnet_sdk_config_deb_url_matches_running_version() -> None:
    """The config-deb URL path segment must be the detected VERSION_ID, never hardcoded."""
    ctx = Ctx(
        os=OsInfo(distro="ubuntu", family="debian", arch="x86_64",
                  version_id="22.04", codename="jammy"),
        ex=FakeExecutor(),
    )
    DotnetSdk().install(ctx)
    blob = " ".join(" ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
    assert "config/ubuntu/22.04/packages-microsoft-prod.deb" in blob
    assert "26.04" not in blob
    assert "resolute" not in blob


def test_dotnet_sdk_verify_on_ubuntu() -> None:
    ctx = _ctx(scripts={"dotnet": Result(0, stdout="10.0.100 [/usr/lib/...]")})
    assert DotnetSdk().verify(ctx) is True


def test_dotnet_sdk_verify_false_when_not_installed_on_ubuntu() -> None:
    ctx = _ctx(scripts={"dotnet": Result(1, stdout="")})
    assert DotnetSdk().verify(ctx) is False


def test_aspire_installs_via_dotnet_tool_on_ubuntu() -> None:
    ctx = _ctx()
    Aspire().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["dotnet", "tool", "install", "-g", "Aspire.Cli"] in calls
    assert not any("apt-get" in " ".join(c) for c in calls)


def test_dotnet_lsp_installs_csharp_tools_on_ubuntu() -> None:
    ctx = _ctx()
    DotnetLsp().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["dotnet", "tool", "install", "-g", "csharp-ls"] in calls
    assert ["dotnet", "tool", "install", "-g", "csharpier"] in calls


# ---------------------------------------------------------------------------
# data — container-based; DataServices install is a no-op beyond Docker
# ---------------------------------------------------------------------------


def test_data_services_verify_reads_bundled_compose_on_ubuntu() -> None:
    assert DataServices().verify(_ctx()) is True


def test_data_services_install_is_noop_on_ubuntu() -> None:
    ctx = _ctx()
    DataServices().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # No package manager calls — compose template ships in-repo
    assert not any("apt-get" in " ".join(c) for c in calls)
    assert not any("dnf" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# devops — mise-based, cross-distro
# ---------------------------------------------------------------------------


def test_devops_tools_use_mise_on_ubuntu() -> None:
    ctx = _ctx()
    DevopsTools().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    flat = " ".join(calls[0])
    assert "opentofu/opentofu@1.11.6" in flat
    assert "derailed/k9s@0.51.0" in flat
    assert not any("apt-get" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# react-native — JDK via mise; libfuse2 prerequisite on Ubuntu
# ---------------------------------------------------------------------------


def test_android_sdk_installs_libfuse2_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "Android" / "Sdk"))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "libfuse2"] in calls


def test_android_sdk_uses_mise_for_jdk_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "Android" / "Sdk"))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # JDK installed via mise (cross-distro Temurin binary), not via apt
    assert ["mise", "use", "-g", "java@temurin-17"] in calls


def test_android_sdk_provisions_sdkmanager_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "Android" / "Sdk"))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("sdkmanager" in " ".join(c) for c in calls)


def test_android_sdk_writes_profile_d_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "Android" / "Sdk"))
    ctx = _ctx()
    AndroidSdk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("devboost-android.sh" in " ".join(c) for c in calls)


def test_expo_verify_reads_bundled_template_on_ubuntu() -> None:
    assert Expo().verify(_ctx()) is True
