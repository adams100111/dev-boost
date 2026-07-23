from __future__ import annotations

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.code_server import CodeServer


def _ctx() -> Ctx:
    return Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=FakeExecutor())


def test_code_server_installs_and_enables_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "dev")
    monkeypatch.delenv("SUDO_USER", raising=False)
    ctx = _ctx()
    CodeServer().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("code-server.dev/install.sh" in " ".join(c) for c in calls)
    assert ["sudo", "systemctl", "enable", "--now", "code-server@dev"] in calls


def test_code_server_skips_install_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "dev")
    monkeypatch.delenv("SUDO_USER", raising=False)
    ex = FakeExecutor(present={"code-server"})
    ctx = Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)
    CodeServer().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # already installed → no curl|sh, but the service is still (re)enabled (idempotent)
    assert not any("install.sh" in " ".join(c) for c in calls)
    assert ["sudo", "systemctl", "enable", "--now", "code-server@dev"] in calls


def test_code_server_verify_uses_which() -> None:
    assert CodeServer().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"),
                                   ex=FakeExecutor(present={"code-server"}))) is True
    assert CodeServer().verify(_ctx()) is False


def test_code_server_profiles() -> None:
    assert CodeServer.profiles == ("brain-host",)
