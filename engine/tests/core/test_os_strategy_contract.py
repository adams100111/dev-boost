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

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula

_OS: dict[str, OsInfo] = {
    "fedora": OsInfo("fedora", "fedora", "x86_64"),
    "debian": OsInfo("ubuntu", "debian", "x86_64"),
    "arch": OsInfo("arch", "arch", "x86_64"),
    "macos": OsInfo("macos", "macos", "aarch64"),
}

#: Modules whose own install finishes its strategy's work with extra steps (Zed writes its
#: config and default-app handlers after the cask). The strategy's calls must be a prefix
#: of the module's; the extra calls may use only the listed tools, and may end (only as
#: the last entry) in NeedsUser or in one of the listed exception types. Under a bare
#: FakeExecutor Zed stops at "utiluti not found", an InstallError.
_EXTENDS: dict[str, tuple[set[str], set[str]]] = {
    "zed": ({"brew", "utiluti"}, {"InstallError"}),
}
_NEEDS_USER = "<needs-user>"
_RAISED = "<raised>"
_MARKERS = {_NEEDS_USER, _RAISED}
#: How much of an exception's message is compared (with its type name): enough to tell
#: two failures of one type apart, short enough to leave out per-run paths.
_MSG_PREFIX = 40

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
    """What ``fn`` ran, ending with how it stopped if it raised.

    Each call starts from the same empty HOME (same path, so argv stays comparable): a
    stateful strategy, such as a launchd writer that skips an already-loaded job, must not
    see what the previous call left behind.
    """
    home = Path(os.environ["HOME"])
    shutil.rmtree(home)
    home.mkdir()
    ex = FakeExecutor()
    try:
        fn(Ctx(os=ctx_os, ex=ex))
    except NeedsUser as e:
        ex.calls.append([_NEEDS_USER, e.reason])
    except Exception as e:  # any other outcome is compared, not a crash of this test
        ex.calls.append([_RAISED, type(e).__name__, str(e)[:_MSG_PREFIX]])
    return ex.calls


@pytest.mark.parametrize(
    ("name", "cls", "key"), _CASES, ids=[f"{n}-{k}" for n, _, k in _CASES]
)
def test_install_and_verify_hand_off_to_the_declared_strategy(
    name: str, cls: type[Module], key: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    os_info = _OS[key]
    strategy = getattr(cls.per_os, key)
    assert isinstance(strategy, Installer)
    assert cls().os_strategy(Ctx(os=os_info, ex=FakeExecutor())) is strategy

    install = _calls(cls().install, os_info)
    verify = _calls(cls().verify, os_info)
    want_install = _calls(strategy.install, os_info)
    if name in _EXTENDS:
        tools, may_raise = _EXTENDS[name]
        assert install[: len(want_install)] == want_install, name
        extra = install[len(want_install):]
        tail = extra.pop() if extra and extra[-1][0] in _MARKERS else None
        assert not [c for c in extra if c[0] in _MARKERS], f"{name}: a marker before the end"
        added = {c[0] for c in extra} - tools
        assert not added, f"{name} adds {sorted(added)}"
        if tail is not None and tail[0] == _RAISED:
            assert tail[1] in may_raise, f"{name} ends in {tail[1]}: {tail[2]}"
    else:
        assert install == want_install, name
    assert verify == _calls(strategy.verify, os_info), name
    if key == "macos" and isinstance(strategy, BrewFormula | BrewCask):
        argv0 = {c[0] for c in install + verify}
        allowed = _EXTENDS[name][0] if name in _EXTENDS else {"brew"}
        assert argv0 <= allowed | _MARKERS, f"{name} runs {sorted(argv0)} on macOS"
