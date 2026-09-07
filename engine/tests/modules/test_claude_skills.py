from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.claude_skills import ClaudeSkills

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _write_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "version": 3,
                "skills": {
                    "caveman": {"source": "mattpocock/skills", "sourceType": "github"},
                    "tdd": {"source": "cursor/plugins", "sourceType": "github"},
                },
            }
        ),
        encoding="utf-8",
    )


def test_install_adds_each_missing_lock_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    ctx = _ctx(present={"npx"})
    ClaudeSkills().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("skills add mattpocock/skills@caveman -g -y" in j for j in joined)
    assert any("skills add cursor/plugins@tdd -g -y" in j for j in joined)


def test_install_skips_already_present_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    # caveman already surfaced under ~/.claude/skills → not re-added
    present_skill = tmp_path / ".claude" / "skills" / "caveman"
    present_skill.mkdir(parents=True)
    ctx = _ctx(present={"npx"})
    ClaudeSkills().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert not any("@caveman" in j for j in joined)
    assert any("@tdd" in j for j in joined)


def test_verify_true_when_all_lock_entries_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    for name in ("caveman", "tdd"):
        (tmp_path / ".claude" / "skills" / name).mkdir(parents=True)
    assert ClaudeSkills().verify(_ctx()) is True
