from __future__ import annotations

import pytest

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, DnfRepo

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("arch", "arch", "x86_64")


# ---------------------------------------------------------------------------
# Fedora / Dnf paths
# ---------------------------------------------------------------------------


def test_install_uses_dnf_on_fedora() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=FEDORA, ex=ex), "git", "curl")
    assert ["sudo", "dnf", "install", "-y", "git", "curl"] in ex.calls


def test_install_with_source_adds_repo_then_installs_refresh() -> None:
    ex = FakeExecutor()
    src: pkg.Source = OsMap[DnfRepo | AptRepo](
        fedora=DnfRepo("ddev", "https://pkg.ddev.com/yum/", gpgcheck=False)
    )
    pkg.install(Ctx(os=FEDORA, ex=ex), "ddev", source=src, refresh=True)
    assert ["sudo", "tee", "/etc/yum.repos.d/ddev.repo"] in ex.calls
    assert ["sudo", "dnf", "install", "--refresh", "-y", "ddev"] in ex.calls


def test_install_resolves_per_os_name() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", default="fd")
    pkg.install(Ctx(os=FEDORA, ex=ex), name)
    assert ["sudo", "dnf", "install", "-y", "fd-find"] in ex.calls


def test_dnf_install_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="no such package")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=FEDORA, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


def test_dnf_add_repo_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"tee": Result(1, stderr="permission denied")})
    repo = DnfRepo("test-repo", "https://example.com/repo/", gpgcheck=False)
    with pytest.raises(InstallError) as exc_info:
        pkg.manager_for(FEDORA).add_repo(Ctx(os=FEDORA, ex=ex), repo)
    assert exc_info.value.code == 1


def test_install_refresh_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="GPG check failed")})
    src: pkg.Source = OsMap[DnfRepo | AptRepo](
        fedora=DnfRepo("myrepo", "https://example.com/", gpgcheck=False)
    )
    with pytest.raises(InstallError):
        pkg.install(Ctx(os=FEDORA, ex=ex), "mypkg", source=src, refresh=True)


# ---------------------------------------------------------------------------
# Ubuntu / Apt paths
# ---------------------------------------------------------------------------


def test_manager_for_debian_family_returns_apt() -> None:
    mgr = pkg.manager_for(UBUNTU)
    assert isinstance(mgr, pkg.Apt)


def test_install_uses_apt_get_on_ubuntu() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=UBUNTU, ex=ex), "git", "curl")
    assert ["sudo", "apt-get", "install", "-y", "git", "curl"] in ex.calls


def test_apt_installed_uses_dpkg() -> None:
    ex = FakeExecutor(scripts={"dpkg": Result(0)})
    assert pkg.installed(Ctx(os=UBUNTU, ex=ex), "git") is True
    assert ["dpkg", "-s", "git"] in ex.calls


def test_apt_install_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"apt-get": Result(1, stderr="unable to fetch")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=UBUNTU, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


def test_apt_add_repo_writes_list_and_updates() -> None:
    ex = FakeExecutor()
    repo = AptRepo(
        list_line="deb https://download.example.com/linux/ubuntu focal stable",
        key_url="https://download.example.com/linux/ubuntu/gpg",
    )
    pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    flat = [" ".join(c) for c in ex.calls]
    assert any("keyrings/download-example-com" in s for s in flat)
    assert any("sources.list.d/download-example-com" in s for s in flat)
    assert any("apt-get update" in s for s in flat)


def test_apt_add_repo_no_key_skips_keyring() -> None:
    ex = FakeExecutor()
    repo = AptRepo(
        list_line="deb https://ppa.example.com/ubuntu focal main",
        key_url="",
    )
    pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    assert not any("keyrings" in " ".join(c) for c in ex.calls)
    assert any("sources.list.d" in " ".join(c) for c in ex.calls)


def test_apt_add_repo_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"tee": Result(1, stderr="permission denied")})
    repo = AptRepo(
        list_line="deb https://pkg.example.com/ubuntu focal stable",
        key_url="",
    )
    with pytest.raises(InstallError) as exc_info:
        pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    assert exc_info.value.code == 1


def test_install_per_os_name_resolves_on_ubuntu() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", debian="fd", default="fd")
    pkg.install(Ctx(os=UBUNTU, ex=ex), name)
    assert ["sudo", "apt-get", "install", "-y", "fd"] in ex.calls


# ---------------------------------------------------------------------------
# Unsupported OS
# ---------------------------------------------------------------------------


def test_unsupported_os_raises() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        pkg.install(Ctx(os=ARCH, ex=ex), "git")
