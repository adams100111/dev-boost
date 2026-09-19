"""Test doubles for macOS system tools (no real `defaults` is ever run in tests).

The other two shared fakes: `tests/scripted.py` (`Scripted`, canned per-argv results) and
`tests.passstore.fakes.RuleExecutor` (token rules), which `PrefsExecutor` builds on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import Result
from tests.passstore.fakes import RuleExecutor

_WRITE_TYPES = {"-bool": "boolean", "-int": "integer", "-float": "float", "-string": "string"}


@dataclass
class PrefsExecutor(RuleExecutor):
    """A stateful fake of `defaults`.

    ``prefs[(domain, key)] = (type, raw)`` where *type* is what ``defaults read-type``
    names (``boolean``/``integer``/``float``/``string``/``array``…) and *raw* is what
    ``defaults read`` prints (bools as ``1``/``0``). Writes and deletes update it.

    A matching ``rules`` entry wins over the store (e.g. to make a ``defaults write``
    fail). Any other argv behaves like ``FakeExecutor`` (``scripts`` by argv[0], else 0).
    """

    prefs: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

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
        res = super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if any(all(t in argv for t in tokens) for tokens, _ in self.rules):
            return res
        if len(argv) < 4 or argv[0] != "defaults":
            return self.scripts.get(argv[0], res) if argv else res
        verb, domain, key = argv[1], argv[2], argv[3]
        cur = self.prefs.get((domain, key))
        if verb == "read-type":
            if cur is None:
                return Result(1, "", f"Could not find key '{key}' in domain '{domain}'\n")
            return Result(0, f"Type is {cur[0]}\n")
        if verb == "read":
            return Result(0, cur[1] + "\n") if cur is not None else Result(1)
        if verb == "write":
            flag, raw = argv[4], argv[5]
            if flag == "-bool":
                raw = "1" if raw == "true" else "0"
            self.prefs[(domain, key)] = (_WRITE_TYPES[flag], raw)
            return Result(0)
        if verb == "delete":
            return Result(0) if self.prefs.pop((domain, key), None) is not None else Result(1)
        return res
