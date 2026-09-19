from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module
from devboost.modules.claude_skills import ClaudeSkills, install_dir_name
from devboost.modules.codex_skills import CodexSkills

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


# --- M3 AF4: a lock-file display name vs the directory the CLI installs into ------------


def _write_display_name_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    entry = {"source": "cursor/plugins", "skillPath": "pstack/skills/poteto-mode/SKILL.md"}
    lock.write_text(json.dumps({"version": 3, "skills": {"Poteto Mode": entry}}), "utf-8")


@pytest.mark.parametrize("mod_cls", [ClaudeSkills, CodexSkills])
def test_display_name_skill_installed_under_its_sanitized_dir_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mod_cls: type[Module]
) -> None:
    # `npx skills add` keys the lock by SKILL.md `name` ("Poteto Mode") but installs into
    # sanitizeName(name) ("poteto-mode"): verify looked for "Poteto Mode" and never found it.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    _write_display_name_lock(tmp_path)
    for d in (".agents/skills/poteto-mode", ".claude/skills/poteto-mode"):
        (tmp_path / d).mkdir(parents=True)
    ex = FakeExecutor(present={"npx"})
    [res] = run_plan([PlannedModule(mod_cls.name)], {mod_cls.name: mod_cls}, Ctx(FEDORA, ex))
    assert res.status == "skip"
    assert not any("skills" in c for c in ex.calls)


def test_install_dir_name_mirrors_the_skills_cli_sanitize_name() -> None:
    assert install_dir_name("Poteto Mode") == "poteto-mode"
    assert install_dir_name("caveman") == "caveman"
    assert install_dir_name("..Weird  Name!!") == "weird-name"
    assert install_dir_name("v1.2_x") == "v1.2_x"
    assert install_dir_name("!!!") == "unnamed-skill"
