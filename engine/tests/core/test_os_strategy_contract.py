"""A module with a per_os entry AND its own install()/verify() must hand off to the entry.

Its own install() is the Linux path. If it forgets the ``os_strategy`` hand-off, a Mac
would silently run the Linux installer (dnf / apt / ``curl … | sh``). This test runs every
such registered module on each OS it declares and checks the executor saw exactly what
the declared strategy alone would do — and, on macOS, nothing but brew.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Installer, Module

_OS: dict[str, OsInfo] = {
    "fedora": OsInfo("fedora", "fedora", "x86_64"),
    "debian": OsInfo("ubuntu", "debian", "x86_64"),
    "arch": OsInfo("arch", "arch", "x86_64"),
    "macos": OsInfo("macos", "macos", "aarch64"),
}


def _own_install_with_per_os() -> list[tuple[str, type[Module]]]:
    return [
        (name, cls) for name, cls in sorted(load().items())
        if cls.install is not Module.install
        and any(getattr(cls.per_os, key) is not None for key in _OS)
    ]


def _cases() -> list[tuple[str, type[Module], str]]:
    return [
        (name, cls, key)
        for name, cls in _own_install_with_per_os()
        for key in _OS
        if getattr(cls.per_os, key) is not None
    ]


def test_there_are_modules_to_check() -> None:
    # Guards against the parametrisation below going vacuous.
    assert _own_install_with_per_os()


def _calls(fn: Callable[[Ctx], object], ctx_os: OsInfo) -> list[list[str]]:
    ex = FakeExecutor()
    fn(Ctx(os=ctx_os, ex=ex))
    return ex.calls


@pytest.mark.parametrize(
    ("name", "cls", "key"), _cases(), ids=[f"{n}-{k}" for n, _, k in _cases()]
)
def test_install_and_verify_hand_off_to_the_declared_strategy(
    name: str, cls: type[Module], key: str
) -> None:
    os_info = _OS[key]
    strategy = getattr(cls.per_os, key)
    assert isinstance(strategy, Installer)
    assert cls().os_strategy(Ctx(os=os_info, ex=FakeExecutor())) is strategy

    assert _calls(cls().install, os_info) == _calls(strategy.install, os_info), name
    assert _calls(cls().verify, os_info) == _calls(strategy.verify, os_info), name
    if key == "macos":
        argv0 = {c[0] for c in _calls(cls().install, os_info) + _calls(cls().verify, os_info)}
        assert argv0 <= {"brew"}, f"{name} runs {sorted(argv0)} on macOS"
