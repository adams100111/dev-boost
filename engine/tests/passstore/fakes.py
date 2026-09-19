"""Test doubles shared by passstore, module and CLI tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import FakeExecutor, Result


@dataclass
class RuleExecutor(FakeExecutor):
    """FakeExecutor whose results are chosen by argv content, not just argv[0].

    ``rules`` is ordered; the first rule whose tokens all appear in argv wins.
    ``on_call`` models state changes: when a call's argv contains the trigger token, its
    rule is pushed to the FRONT of ``rules`` (e.g. after `--quick-gen-key`, the key lists).
    """

    rules: list[tuple[tuple[str, ...], Result]] = field(default_factory=list)
    on_call: list[tuple[str, tuple[tuple[str, ...], Result]]] = field(default_factory=list)
    envs: list[dict[str, str]] = field(default_factory=list)
    stdins: list[str | None] = field(default_factory=list)
    interactive: list[bool] = field(default_factory=list)

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
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        self.envs.append(dict(env or {}))
        self.stdins.append(stdin)
        self.interactive.append(interactive)
        for trigger, rule in self.on_call:
            if trigger in argv:
                self.rules.insert(0, rule)
        for tokens, res in self.rules:
            if all(t in argv for t in tokens):
                return res
        return Result(0)


def _escape_colons(uid: str) -> str:
    """Escape a uid the way `gpg --with-colons` does: `:` -> `\\x3a`, `\\` -> `\\x5c`."""
    return uid.replace("\\", "\\x5c").replace(":", "\\x3a")


def colons(kind: str, fp: str, *uids: str) -> str:
    """Minimal `gpg --with-colons` output for one key (primary + one subkey)."""
    lines = [f"{kind}:u:255:22:{fp[-16:]}:1700000000:::u:::scESC:::+:::ed25519:::0:",
             f"fpr:::::::::{fp}:"]
    lines += [
        f"uid:u::::1700000000::HASH::{_escape_colons(u)}::::::::::0:" for u in uids
    ]
    lines += ["ssb:u:255:18:SUBKEYID:1700000000::::::e:::+:::cv25519::", "fpr:::::::::SUBFPR:"]
    return "\n".join(lines) + "\n"
