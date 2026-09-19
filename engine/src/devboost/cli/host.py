"""macOS invocation rules: who may run devboost, which commands exist, and the session.

Kept out of the Typer wiring so each rule is a plain, testable function.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType

from devboost.core import log
from devboost.core.osinfo import OsInfo

LINUX_ONLY: frozenset[str] = frozenset({"installer", "accounts", "brain"})


def invocation_error(os_info: OsInfo, subcommand: str | None, euid: int) -> str | None:
    """Why this invocation must not proceed on this OS, or None."""
    if os_info.family != "macos":
        return None
    if euid == 0:
        return (
            "don't run devboost as root on macOS — Homebrew refuses to run as root. "
            "Run it as your user; dev-boost asks for sudo itself when a step needs it."
        )
    if subcommand in LINUX_ONLY:
        return f"`devboost {subcommand}` is Linux-only"
    return None


def _run_quiet(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


class SudoKeepalive:
    """Ask for the sudo password once, then keep the timestamp fresh until exit.

    The same approach the Homebrew installer uses: the user types their password at the
    start and can walk away instead of being prompted again mid-run.
    """

    def __init__(self, run: Callable[[list[str]], int] = _run_quiet, interval: float = 60.0):
        self._run = run
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Whether ``sudo -v`` succeeded, i.e. this session holds a sudo timestamp.
        self.granted = False

    def __enter__(self) -> SudoKeepalive:
        if self._run(["sudo", "-v"]) != 0:
            log.warn("sudo not granted — steps that need it are skipped as blocked")
            return self
        self.granted = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._run(["sudo", "-n", "-v"])

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)


def keep_awake(popen: Callable[[list[str]], object] = subprocess.Popen) -> object | None:
    """Stop the Mac sleeping mid-install; caffeinate exits on its own when we do."""
    try:
        return popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    except OSError:
        log.warn("caffeinate unavailable — the Mac may sleep during a long install")
        return None


@contextmanager
def mac_session(os_info: OsInfo, *, dry_run: bool, sudo: bool = True) -> Iterator[bool]:
    """Keep-awake for a real install run on macOS, plus one sudo prompt when ``sudo``.

    The caller passes ``sudo=False`` when no pending step needs root, so a re-run on a
    set-up Mac never asks for a password. A no-op off macOS and in a dry run.

    Yields whether the session holds sudo: False on macOS when it was not asked for or
    not granted (an unattended run has no tty to type the password on), True otherwise.
    """
    if os_info.family != "macos" or dry_run:
        yield True
        return
    keep_awake()
    if not sudo:
        yield False
        return
    with SudoKeepalive() as keepalive:
        yield keepalive.granted
