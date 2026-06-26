"""The single side-effect seam. All system-tool invocation passes through an Executor."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    ) -> Result: ...

    def which(self, cmd: str) -> bool: ...


class RealExecutor:
    """Runs argv lists via subprocess — never a shell string."""

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        cmd = (["sudo", *argv]) if sudo else list(argv)
        proc = subprocess.run(
            cmd,
            input=stdin,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
        return Result(code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def which(self, cmd: str) -> bool:
        return _which(cmd) is not None


@dataclass
class FakeExecutor:
    """Recording fake for hermetic tests.

    Records every command as an argv list (sudo-prefixed) in `calls`. Returns Result(0)
    by default; `scripts` maps the first argv token to a canned Result; `present` is the
    set of commands `which` reports as found.
    """

    calls: list[list[str]] = field(default_factory=list)
    scripts: dict[str, Result] = field(default_factory=dict)
    present: set[str] = field(default_factory=set)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        recorded = (["sudo", *argv]) if sudo else list(argv)
        self.calls.append(recorded)
        return self.scripts.get(argv[0], Result(0)) if argv else Result(0)

    def which(self, cmd: str) -> bool:
        return cmd in self.present
