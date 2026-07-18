"""The single side-effect seam. All system-tool invocation passes through an Executor."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which as _which
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Result:
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


@runtime_checkable
class Executor(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> Result: ...

    def which(self, cmd: str) -> bool: ...


def _prepend_mise_dirs(path: str) -> str:
    """Return *path* with the user tool dirs prepended (if not already present).

    Ensures tools found in subprocesses even on a fresh firstboot where the user's shell
    profile has not been sourced: ``mise`` shims (node, pnpm, bun, …), ``~/.local/bin``, and
    ``~/.dotnet/tools`` (where ``dotnet tool install -g`` puts aspire, csharp-ls, csharpier).
    """
    try:
        home = Path.home()
    except RuntimeError:
        return path
    prepend = [
        str(home / ".local" / "share" / "mise" / "shims"),
        str(home / ".local" / "bin"),
        str(home / ".dotnet" / "tools"),
    ]
    existing = path.split(os.pathsep) if path else []
    new_parts = [p for p in prepend if p not in existing]
    return os.pathsep.join([*new_parts, *existing]) if new_parts else path


class RealExecutor:
    """Runs argv lists via subprocess — never a shell string.

    All subprocess invocations receive an environment derived from ``os.environ`` with
    ``~/.local/share/mise/shims`` and ``~/.local/bin`` prepended to PATH.  This ensures
    mise-managed tools are discoverable immediately after ``mise install`` without waiting
    for a new shell login.

    ``cwd`` runs the command in a directory: some third-party scripts resolve their own
    helpers relative to the caller's working directory, so it is part of the contract, not
    a convenience.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> Result:
        cmd = (["sudo", *argv]) if sudo else list(argv)
        # Start from the full process environment so that PATH, HOME, USER, etc. are
        # available.  Then prepend mise shims unconditionally.
        base: dict[str, str] = {
            **os.environ,
            "PATH": _prepend_mise_dirs(os.environ.get("PATH", "")),
        }
        if env is not None:
            # Caller-supplied overrides take precedence, but we still ensure mise dirs
            # appear at the front of whatever PATH the caller chose.
            caller_path = env.get("PATH", base["PATH"])
            effective: dict[str, str] = {
                **base, **dict(env), "PATH": _prepend_mise_dirs(caller_path),
            }
        else:
            effective = base
        try:
            proc = subprocess.run(
                cmd,
                input=stdin,
                env=effective,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            # The command (or sudo) was not found / not executable.  Report this as the
            # conventional shell "command not found" exit code (127) rather than raising,
            # so callers — notably verify() probes for not-yet-installed tools — see a
            # non-ok Result instead of an unhandled traceback.
            return Result(code=127, stderr=f"{cmd[0]}: {exc.strerror}")
        return Result(code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def which(self, cmd: str) -> bool:
        return _which(cmd, path=_prepend_mise_dirs(os.environ.get("PATH", ""))) is not None


@dataclass
class FakeExecutor:
    """Recording fake for hermetic tests.

    Records every command as an argv list (sudo-prefixed) in ``calls``.  Returns
    ``Result(0)`` by default; ``scripts`` maps the first argv token to a canned
    ``Result``; ``present`` is the set of commands ``which`` reports as found.
    """

    calls: list[list[str]] = field(default_factory=list)
    scripts: dict[str, Result] = field(default_factory=dict)
    present: set[str] = field(default_factory=set)
    #: cwd of each recorded call, index-aligned with ``calls`` (None = caller's directory).
    cwds: list[Path | None] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> Result:
        recorded = (["sudo", *argv]) if sudo else list(argv)
        self.calls.append(recorded)
        self.cwds.append(cwd)
        return self.scripts.get(argv[0], Result(0)) if argv else Result(0)

    def which(self, cmd: str) -> bool:
        return cmd in self.present


class DemotingExecutor:
    """Run as root, but demote unprivileged commands to *target_user*.

    Used by the accounts bootstrap: the engine runs as root, so sudo=True commands
    execute directly, while sudo=False commands (user-scoped writes to the user's HOME)
    are wrapped in ``sudo -u <user> -H`` so they run as — and create files owned by — the
    target user.
    """

    def __init__(self, inner: Executor, target_user: str) -> None:
        self._inner = inner
        self._user = target_user

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> Result:
        if sudo:
            return self._inner.run(argv, sudo=False, stdin=stdin, env=env, cwd=cwd)
        wrapped = ["sudo", "-u", self._user, "-H", *argv]
        return self._inner.run(wrapped, sudo=False, stdin=stdin, env=env, cwd=cwd)

    def which(self, cmd: str) -> bool:
        return self._inner.which(cmd)
