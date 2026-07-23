from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.caddy import Caddy


def _ubuntu() -> Ctx:
    return Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=FakeExecutor())


def _fedora() -> Ctx:
    return Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())


def test_caddy_installs_on_debian_via_cloudsmith_apt() -> None:
    ctx = _ubuntu()
    Caddy().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # apt repo written, then caddy installed
    assert ["sudo", "tee", "/etc/apt/sources.list.d/dl-cloudsmith-io.list"] in calls
    assert ["sudo", "apt-get", "install", "-y", "caddy"] in calls


def test_caddy_installs_on_fedora_via_copr() -> None:
    ctx = _fedora()
    Caddy().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(
        c[:3] == ["sudo", "sh", "-c"] and "copr enable" in c[3] and "caddy" in c[3] for c in calls
    )


def test_caddy_unsupported_os_raises() -> None:
    from devboost.core.errors import UnsupportedOS

    ctx = Ctx(os=OsInfo("arch", "arch", "x86_64"), ex=FakeExecutor())
    import pytest

    with pytest.raises(UnsupportedOS):
        Caddy().install(ctx)


def test_caddy_verify_uses_which() -> None:
    ex = FakeExecutor(present={"caddy"})
    assert Caddy().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)) is True
    assert Caddy().verify(_ubuntu()) is False


def test_caddy_profiles() -> None:
    assert Caddy.profiles == ("brain-host",)
