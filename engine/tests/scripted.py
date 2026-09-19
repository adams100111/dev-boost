"""A FakeExecutor that answers by argv prefix — for code that calls one tool several ways."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import FakeExecutor, Result


@dataclass
class Scripted(FakeExecutor):
    """``answers`` maps an argv prefix to a Result; the longest matching prefix wins, then
    ``scripts`` (by argv[0]), then Result(0). ``envs`` / ``interactives`` record each call's
    ``env`` and ``interactive`` arguments, index-aligned with ``calls``.

    See also P2's ``tests.passstore.fakes.RuleExecutor`` (ordered token rules, not argv
    prefixes); both are kept on purpose (ruling C-R10)."""

    answers: dict[tuple[str, ...], Result] = field(default_factory=dict)
    envs: list[Mapping[str, str] | None] = field(default_factory=list)
    interactives: list[bool] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        default = super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive
        )
        self.envs.append(env)
        self.interactives.append(interactive)
        key = tuple(argv)
        for n in range(len(key), 0, -1):
            if key[:n] in self.answers:
                return self.answers[key[:n]]
        return default
