from __future__ import annotations

from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.ddev import Ddev
from devboost.modules.docker import Docker
from devboost.modules.ripgrep import Ripgrep


def test_ripgrep_installs_via_dnf(fedora_ctx: Ctx) -> None:
    Ripgrep().install(fedora_ctx)
    assert ["sudo", "dnf", "install", "-y", "ripgrep"] in fedora_ctx.ex.calls  # type: ignore[attr-defined]


def test_ripgrep_verify_uses_which() -> None:
    from devboost.core.osinfo import OsInfo

    ex = FakeExecutor(present={"rg"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    assert Ripgrep().verify(ctx) is True


def test_ddev_requires_docker() -> None:
    assert Docker in Ddev.requires


def test_ddev_installs_repo_then_dnf_then_mkcert(fedora_ctx: Ctx) -> None:
    Ddev().install(fedora_ctx)
    calls = fedora_ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "tee", "/etc/yum.repos.d/ddev.repo"] in calls
    assert ["sudo", "dnf", "install", "--refresh", "-y", "ddev"] in calls
    assert ["mkcert", "-install"] in calls
