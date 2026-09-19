"""Per-call ``timeout`` on the Executor API (M4-W0 fix I1)."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from devboost.exec.executor import (
    DemotingExecutor,
    FakeExecutor,
    NoPromptSudoExecutor,
    RealExecutor,
    Result,
)


def test_real_executor_turns_a_timeout_into_a_failed_result() -> None:
    res = RealExecutor().run(
        [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3
    )
    assert not res.ok
    assert res.code == 124
    assert "timed out" in res.stderr


def test_real_executor_without_timeout_still_runs() -> None:
    assert RealExecutor().run([sys.executable, "-c", "pass"], timeout=None).ok


def test_fake_executor_accepts_a_timeout() -> None:
    ex = FakeExecutor()
    assert ex.run(["docker", "info"], timeout=5.0).ok
    assert ex.calls == [["docker", "info"]]


class _Inner(FakeExecutor):
    timeouts: list[float | None]

    def __init__(self) -> None:
        super().__init__()
        self.timeouts = []

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        self.timeouts.append(timeout)
        return super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd,
                           interactive=interactive, timeout=timeout)


def test_wrappers_pass_the_timeout_through() -> None:
    inner = _Inner()
    NoPromptSudoExecutor(inner).run(["docker", "info"], timeout=7.0)
    DemotingExecutor(inner, "alice").run(["docker", "info"], timeout=8.0)
    DemotingExecutor(inner, "alice").run(["true"], sudo=True, timeout=9.0)
    assert inner.timeouts == [7.0, 8.0, 9.0]
