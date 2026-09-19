"""A module with a per_os entry AND its own install() or verify() must hand off to the entry.

Its own install() is the Linux path. If it forgets the ``os_strategy`` hand-off, a Mac
would silently run the Linux installer (dnf / apt / ``curl … | sh``). This test runs every
such registered module on each OS it declares and checks the executor saw exactly what
the declared strategy alone would do (a raised NeedsUser or other error counts as an
outcome, so a strategy that stops with `blocked` is compared too). A plain brew strategy
must run nothing but brew on macOS. A module in ``_EXTENDS`` may add steps after its
strategy's, using only the tools listed for it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Installer, Module
from devboost.modules import server
from devboost.modules._brew import BrewCask, BrewFormula

_OS: dict[str, OsInfo] = {
    "fedora": OsInfo("fedora", "fedora", "x86_64"),
    "debian": OsInfo("ubuntu", "debian", "x86_64"),
    "arch": OsInfo("arch", "arch", "x86_64"),
    "macos": OsInfo("macos", "macos", "aarch64"),
}

#: Modules whose own install finishes its strategy's work with extra steps (Zed writes its
#: config and default-app handlers after the cask). The strategy's calls must be a prefix
#: of the module's, and the extra calls may use only these tools.
_EXTENDS: dict[str, set[str]] = {"zed": {"brew", "utiluti"}}
_NEEDS_USER = "<needs-user>"


def _own_install_or_verify_with_per_os() -> list[tuple[str, type[Module]]]:
    return [
        (name, cls) for name, cls in sorted(load().items())
        if (cls.install is not Module.install or cls.verify is not Module.verify)
        and any(getattr(cls.per_os, key) is not None for key in _OS)
    ]


def _cases() -> list[tuple[str, type[Module], str]]:
    return [
        (name, cls, key)
        for name, cls in _own_install_or_verify_with_per_os()
        for key in _OS
        if getattr(cls.per_os, key) is not None
    ]


_CASES = _cases()


def test_there_are_modules_to_check() -> None:
    # Guards against the parametrisation below going vacuous.
    assert _own_install_or_verify_with_per_os()


def _calls(fn: Callable[[Ctx], object], ctx_os: OsInfo) -> list[list[str]]:
    """What ``fn`` ran, ending with how it stopped if it raised."""
    ex = FakeExecutor()
    try:
        fn(Ctx(os=ctx_os, ex=ex))
    except NeedsUser as e:
        ex.calls.append([_NEEDS_USER, e.reason])
    except Exception as e:  # any other outcome is compared, not a crash of this test
        ex.calls.append(["<raised>", type(e).__name__])
    return ex.calls


@pytest.mark.parametrize(
    ("name", "cls", "key"), _CASES, ids=[f"{n}-{k}" for n, _, k in _CASES]
)
def test_install_and_verify_hand_off_to_the_declared_strategy(
    name: str, cls: type[Module], key: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    # Hermetic: the host's own /Applications/Tailscale.app must not change the outcome.
    monkeypatch.setattr(server, "_TS_APP", tmp_path / "absent" / "Tailscale.app")
    os_info = _OS[key]
    strategy = getattr(cls.per_os, key)
    assert isinstance(strategy, Installer)
    assert cls().os_strategy(Ctx(os=os_info, ex=FakeExecutor())) is strategy

    install = _calls(cls().install, os_info)
    verify = _calls(cls().verify, os_info)
    want_install = _calls(strategy.install, os_info)
    if name in _EXTENDS:
        assert install[: len(want_install)] == want_install, name
        extra = {c[0] for c in install[len(want_install):]} - {_NEEDS_USER}
        assert extra <= _EXTENDS[name], f"{name} adds {sorted(extra)}"
    else:
        assert install == want_install, name
    assert verify == _calls(strategy.verify, os_info), name
    if key == "macos" and isinstance(strategy, BrewFormula | BrewCask):
        argv0 = {c[0] for c in install + verify}
        allowed = _EXTENDS.get(name, {"brew"})
        assert argv0 <= allowed | {_NEEDS_USER}, f"{name} runs {sorted(argv0)} on macOS"
