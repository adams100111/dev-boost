from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.model import Ctx
from devboost.modules.codex_skills import CodexSkills
from tests.modules.test_claude_skills import SkillsCli

FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "root", tmp_path / "root")  # no repo-vendored skills
    return tmp_path


def _write_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"version": 3, "skills": {"caveman": {"source": "mattpocock/skills"}}}),
        encoding="utf-8",
    )


def test_install_adds_lock_entry_for_codex(_home: Path) -> None:
    _write_lock(_home)
    ex = SkillsCli(present={"npx"}, served={"caveman"})
    CodexSkills().install(Ctx(FEDORA, ex))
    joined = [" ".join(c) for c in ex.calls]
    assert any("skills add mattpocock/skills@caveman -g -y" in j for j in joined)
    assert CodexSkills().verify(Ctx(FEDORA, ex))


def test_install_skips_present_codex_skill(_home: Path) -> None:
    _write_lock(_home)
    (_home / ".agents" / "skills" / "caveman").mkdir(parents=True)
    ex = SkillsCli(present={"npx"})
    CodexSkills().install(Ctx(FEDORA, ex))
    assert not any("@caveman" in " ".join(c) for c in ex.calls)
