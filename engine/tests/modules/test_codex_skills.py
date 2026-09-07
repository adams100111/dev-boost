from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.codex_skills import CodexSkills

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _write_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"version": 3, "skills": {"caveman": {"source": "mattpocock/skills"}}}),
        encoding="utf-8",
    )


def test_install_adds_lock_entry_for_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    ctx = _ctx(present={"npx"})
    CodexSkills().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("skills add mattpocock/skills@caveman -g -y" in j for j in joined)


def test_install_skips_present_codex_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    (tmp_path / ".agents" / "skills" / "caveman").mkdir(parents=True)
    ctx = _ctx(present={"npx"})
    CodexSkills().install(ctx)
    assert not any("@caveman" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
