from __future__ import annotations

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor
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
