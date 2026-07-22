from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.mosh import Mosh


def test_mosh_installs_via_dnf(fedora_ctx: Ctx) -> None:
    Mosh().install(fedora_ctx)
    assert ["sudo", "dnf", "install", "-y", "mosh"] in fedora_ctx.ex.calls  # type: ignore[attr-defined]


def test_mosh_installs_via_apt(ubuntu_os: OsInfo) -> None:
    ex = FakeExecutor()
    Mosh().install(Ctx(os=ubuntu_os, ex=ex))
    assert ["sudo", "apt-get", "install", "-y", "mosh"] in ex.calls


def test_mosh_verify_uses_which() -> None:
    ex = FakeExecutor(present={"mosh"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    assert Mosh().verify(ctx) is True
    assert Mosh().verify(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())) is False


def test_mosh_is_in_remote_profile_only() -> None:
    assert Mosh.profiles == ("remote",)
