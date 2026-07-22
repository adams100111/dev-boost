from __future__ import annotations

import tomllib

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.herdr import Herdr

FEDORA_X86 = OsInfo(distro="fedora", family="fedora", arch="x86_64")
FEDORA_ARM = OsInfo(distro="fedora", family="fedora", arch="aarch64")


def _ctx(os_: OsInfo = FEDORA_X86, **kw: object) -> Ctx:
    return Ctx(os=os_, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_herdr_is_optional_agents_profile() -> None:
    assert Herdr.profiles == ("optional-agents",)
    assert Herdr.category == "optional-agents"


def test_herdr_verify_uses_which() -> None:
    assert Herdr().verify(_ctx(present=set())) is False
    assert Herdr().verify(_ctx(present={"herdr"})) is True


def test_herdr_install_downloads_verified_x86_64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx()
    Herdr().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert len(calls) == 1 and calls[0][:2] == ["sh", "-c"]
    script = calls[0][2]
    assert "herdr-linux-x86_64" in script
    assert "sha256sum -c -" in script
    assert "/home/tester/.local/bin/herdr" in script


def test_herdr_install_selects_aarch64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(FEDORA_ARM)
    Herdr().install(ctx)
    script = ctx.ex.calls[0][2]  # type: ignore[attr-defined]
    assert "herdr-linux-aarch64" in script


def test_herdr_install_raises_on_checksum_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(scripts={"sh": Result(1, stderr="sha256sum: WARNING")})
    with pytest.raises(InstallError, match="checksum"):
        Herdr().install(ctx)


def test_herdr_install_raises_on_unknown_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(OsInfo(distro="fedora", family="fedora", arch="riscv64"))
    with pytest.raises(InstallError, match="riscv64"):
        Herdr().install(ctx)


def test_optional_agents_profile_registered() -> None:
    data = tomllib.loads(settings.profiles_path.read_text(encoding="utf-8"))
    assert "herdr" in data["profiles"]["optional-agents"]
