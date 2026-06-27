from __future__ import annotations

import pytest

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import Ctx, DnfRepo

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def test_install_uses_dnf_on_fedora() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=FEDORA, ex=ex), "git", "curl")
    assert ["sudo", "dnf", "install", "-y", "git", "curl"] in ex.calls


def test_install_with_source_adds_repo_then_installs_refresh() -> None:
    ex = FakeExecutor()
    src: pkg.Source = OsMap(fedora=DnfRepo("ddev", "https://pkg.ddev.com/yum/", gpgcheck=False))
    pkg.install(Ctx(os=FEDORA, ex=ex), "ddev", source=src, refresh=True)
    assert ["sudo", "tee", "/etc/yum.repos.d/ddev.repo"] in ex.calls
    assert ["sudo", "dnf", "install", "--refresh", "-y", "ddev"] in ex.calls


def test_install_resolves_per_os_name() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", default="fd")
    pkg.install(Ctx(os=FEDORA, ex=ex), name)
    assert ["sudo", "dnf", "install", "-y", "fd-find"] in ex.calls


def test_unsupported_os_raises() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        pkg.install(Ctx(os=UBUNTU, ex=ex), "git")


def test_dnf_install_failure_raises_install_error() -> None:
    """Dnf.install must raise InstallError when dnf exits non-zero."""
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="no such package")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=FEDORA, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


def test_dnf_add_repo_failure_raises_install_error() -> None:
    """Dnf.add_repo must raise InstallError when tee exits non-zero."""
    ex = FakeExecutor(scripts={"tee": Result(1, stderr="permission denied")})
    repo = DnfRepo("test-repo", "https://example.com/repo/", gpgcheck=False)
    with pytest.raises(InstallError) as exc_info:
        pkg.manager_for(FEDORA).add_repo(Ctx(os=FEDORA, ex=ex), repo)
    assert exc_info.value.code == 1


def test_install_refresh_failure_raises_install_error() -> None:
    """The refresh=True code path must also raise InstallError on failure."""
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="GPG check failed")})
    src: pkg.Source = OsMap(fedora=DnfRepo("myrepo", "https://example.com/", gpgcheck=False))
    with pytest.raises(InstallError):
        pkg.install(Ctx(os=FEDORA, ex=ex), "mypkg", source=src, refresh=True)
