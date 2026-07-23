from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.crossarch_build import CrossArchBuild


def _ctx(distro: str, family: str) -> Ctx:
    return Ctx(os=OsInfo(distro, family, "x86_64"), ex=FakeExecutor())


def test_crossarch_installs_podman_and_qemu_on_debian() -> None:
    ctx = _ctx("ubuntu", "debian")
    CrossArchBuild().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "podman", "qemu-user-static"] in calls
    assert ["sudo", "apt-get", "install", "-y", "binfmt-support"] in calls


def test_crossarch_installs_podman_and_qemu_on_fedora() -> None:
    ctx = _ctx("fedora", "fedora")
    CrossArchBuild().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "podman", "qemu-user-static"] in calls


def test_crossarch_verify_uses_which_podman() -> None:
    ex = FakeExecutor(present={"podman"})
    assert CrossArchBuild().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)) is True
    assert CrossArchBuild().verify(_ctx("ubuntu", "debian")) is False


def test_crossarch_profiles() -> None:
    assert CrossArchBuild.profiles == ("brain-host",)
