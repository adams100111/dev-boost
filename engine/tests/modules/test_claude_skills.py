from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.claude_skills import ClaudeSkills, install_dir_name, vendored_targets
from devboost.modules.codex_skills import CodexSkills

FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME and the bundled-source root both live under tmp_path: no real vendored skill
    (the repo's dotfiles vendor some) leaks into a test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(settings, "root", tmp_path / "root")
    return home


def _home() -> Path:
    return Path(os.environ["HOME"])


def _src() -> Path:
    return settings.root / "dotfiles"


@dataclass
class SkillsCli(FakeExecutor):
    """FakeExecutor that behaves like the two tools the modules drive.

    `npx skills add <source>@<name>` installs *name* (content in ~/.agents/skills, a
    ~/.claude/skills symlink) when it is in ``served``; otherwise it fails as the real CLI
    does for a skill upstream renamed or deleted. `chezmoi apply … <targets>` lays each
    target down from the dotfiles source, like the real apply of a plain vendored skill.
    """

    served: set[str] = field(default_factory=set)

    def run(self, argv: Sequence[str], **kw: object) -> Result:
        super().run(argv, **kw)  # type: ignore[arg-type]
        home = _home()
        if list(argv[:3]) == ["npx", "skills", "add"]:
            name = argv[3].split("@", 1)[1]
            if name not in self.served:
                return Result(1, stderr=f"No matching skills found for: {name}")
            (home / ".agents" / "skills" / name).mkdir(parents=True)
            (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
            (home / ".claude" / "skills" / name).symlink_to(f"../../.agents/skills/{name}")
            return Result(0)
        if list(argv[:2]) == ["chezmoi", "apply"]:
            for target in (Path(a) for a in argv if a.startswith(str(home) + "/")):
                src_dir = {".agents": "private_dot_agents", ".claude": "private_dot_claude"}[
                    target.relative_to(home).parts[0]
                ]
                base = _src() / src_dir / "skills"
                if (base / target.name).is_dir():
                    shutil.copytree(base / target.name, target)
                else:
                    target.symlink_to((base / f"symlink_{target.name}").read_text())
            return Result(0)
        return Result(0)


def _write_lock(home: Path, skills: Mapping[str, str] | None = None) -> None:
    skills = skills or {"caveman": "mattpocock/skills", "tdd": "cursor/plugins"}
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    body = {n: {"source": s, "sourceType": "github"} for n, s in skills.items()}
    lock.write_text(json.dumps({"version": 3, "skills": body}), encoding="utf-8")


def _vendor(name: str) -> None:
    """Vendor *name* in the dotfiles source the way the repo does."""
    d = _src() / "private_dot_agents" / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\nvendored\n", encoding="utf-8")
    link = _src() / "private_dot_claude" / "skills" / f"symlink_{name}"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.write_text(f"../../.agents/skills/{name}", encoding="utf-8")


def _run(mod_cls: type[Module], ex: FakeExecutor) -> str:
    [res] = run_plan([PlannedModule(mod_cls.name)], {mod_cls.name: mod_cls}, Ctx(FEDORA, ex))
    return f"{res.status}:{res.detail}"


def test_install_adds_each_missing_lock_entry(_hermetic: Path) -> None:
    _write_lock(_hermetic)
    ex = SkillsCli(present={"npx"}, served={"caveman", "tdd"})
    ClaudeSkills().install(Ctx(FEDORA, ex))
    joined = [" ".join(c) for c in ex.calls]
    assert any("skills add mattpocock/skills@caveman -g -y" in j for j in joined)
    assert any("skills add cursor/plugins@tdd -g -y" in j for j in joined)


def test_install_skips_already_present_skill(_hermetic: Path) -> None:
    _write_lock(_hermetic)
    # caveman already surfaced under ~/.claude/skills → not re-added
    (_hermetic / ".claude" / "skills" / "caveman").mkdir(parents=True)
    ex = SkillsCli(present={"npx"}, served={"tdd"})
    ClaudeSkills().install(Ctx(FEDORA, ex))
    joined = [" ".join(c) for c in ex.calls]
    assert not any("@caveman" in j for j in joined)
    assert any("@tdd" in j for j in joined)


def test_verify_true_when_all_lock_entries_present(_hermetic: Path) -> None:
    _write_lock(_hermetic)
    for name in ("caveman", "tdd"):
        (_hermetic / ".claude" / "skills" / name).mkdir(parents=True)
    assert ClaudeSkills().verify(Ctx(FEDORA, FakeExecutor())) is True


# --- a skill upstream no longer serves: vendored copy, else blocked --------------------


@pytest.mark.parametrize("mod_cls", [ClaudeSkills, CodexSkills])
def test_vendored_entry_installs_from_the_vendor_dir_not_npx(
    _hermetic: Path, mod_cls: type[Module]
) -> None:
    # Upstream dropped caveman: `skills add` would fail with "No matching skills found".
    _write_lock(_hermetic)
    _vendor("caveman")
    ex = SkillsCli(present={"npx", "chezmoi"}, served={"tdd"})
    assert _run(mod_cls, ex) == "ok:"
    assert not any("@caveman" in " ".join(c) for c in ex.calls)
    [apply] = [c for c in ex.calls if c[:2] == ["chezmoi", "apply"]]
    assert apply[apply.index("--source") + 1] == str(_src())
    assert apply[-2:] == [
        str(_hermetic / ".agents" / "skills" / "caveman"),
        str(_hermetic / ".claude" / "skills" / "caveman"),
    ]
    skill = _hermetic / ".claude" / "skills" / "caveman" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").endswith("vendored\n")


@pytest.mark.parametrize("mod_cls", [ClaudeSkills, CodexSkills])
def test_unfetchable_unvendored_entry_is_blocked_not_failed(
    _hermetic: Path, mod_cls: type[Module]
) -> None:
    _write_lock(_hermetic)
    ex = SkillsCli(present={"npx", "chezmoi"}, served={"tdd"})
    status = _run(mod_cls, ex)
    assert status.startswith("blocked:needs-user:")
    assert "caveman (mattpocock/skills)" in status
    assert "dotfiles/private_dot_agents/skills/" in status  # the fix: vendor it …
    assert "dot_skill-lock.json" in status  # … or drop it from the lock
    assert "tdd" not in status.split("→")[0]  # the fetchable one installed fine
    assert "verify-failed" not in status


@pytest.mark.parametrize("mod_cls", [ClaudeSkills, CodexSkills])
def test_rerun_after_block_stays_blocked_never_fails(
    _hermetic: Path, mod_cls: type[Module]
) -> None:
    _write_lock(_hermetic)
    for _ in range(2):
        status = _run(mod_cls, SkillsCli(present={"npx", "chezmoi"}, served={"tdd"}))
        assert status.startswith("blocked:")


def test_vendored_but_unappliable_entry_is_blocked_not_a_verify_loop(_hermetic: Path) -> None:
    # Vendored, but chezmoi is missing: no endless "verify failed after install".
    _write_lock(_hermetic, {"caveman": "mattpocock/skills"})
    _vendor("caveman")
    ex = SkillsCli(present={"npx"})
    status = _run(ClaudeSkills, ex)
    assert status.startswith("blocked:needs-user:")
    assert "vendored caveman did not apply" in status
    assert not any("@caveman" in " ".join(c) for c in ex.calls)


def test_skills_add_that_exits_zero_but_installs_nothing_is_blocked(_hermetic: Path) -> None:
    _write_lock(_hermetic, {"caveman": "mattpocock/skills"})
    ex = FakeExecutor(present={"npx"})  # every command "succeeds", nothing appears
    with pytest.raises(NeedsUser, match="caveman"):
        ClaudeSkills().install(Ctx(FEDORA, ex))


def test_no_npx_names_the_skills_it_could_not_fetch(_hermetic: Path) -> None:
    _write_lock(_hermetic)
    _vendor("caveman")
    with pytest.raises(NeedsUser) as exc:
        ClaudeSkills().install(Ctx(FEDORA, SkillsCli(present={"chezmoi"})))
    assert "npx not found for tdd" in exc.value.reason
    assert "caveman" not in exc.value.reason  # restored from its vendored copy
    assert "Node.js" in exc.value.how_to_fix


def test_vendored_targets_only_lists_what_the_source_vendors(_hermetic: Path) -> None:
    _vendor("caveman")
    assert vendored_targets(_hermetic, "caveman") == [
        _hermetic / ".agents" / "skills" / "caveman",
        _hermetic / ".claude" / "skills" / "caveman",
    ]
    assert vendored_targets(_hermetic, "tdd") == []


def test_repo_vendors_every_skill_upstream_dropped() -> None:
    """The bundled dotfiles carry the eight skills mattpocock/skills renamed or deleted."""
    from devboost.core.settings import Settings

    src = Settings().root / "dotfiles"
    for name in ("caveman", "diagnose", "to-issues", "to-prd", "write-a-skill", "zoom-out",
                 "qa", "design-an-interface"):
        assert (src / "private_dot_agents" / "skills" / name / "SKILL.md").is_file(), name
        link = src / "private_dot_claude" / "skills" / f"symlink_{name}"
        assert link.read_text(encoding="utf-8") == f"../../.agents/skills/{name}", name


# --- M3 AF4: a lock-file display name vs the directory the CLI installs into ------------


def _write_display_name_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    entry = {"source": "cursor/plugins", "skillPath": "pstack/skills/poteto-mode/SKILL.md"}
    lock.write_text(json.dumps({"version": 3, "skills": {"Poteto Mode": entry}}), "utf-8")


@pytest.mark.parametrize("mod_cls", [ClaudeSkills, CodexSkills])
def test_display_name_skill_installed_under_its_sanitized_dir_verifies(
    _hermetic: Path, monkeypatch: pytest.MonkeyPatch, mod_cls: type[Module]
) -> None:
    # `npx skills add` keys the lock by SKILL.md `name` ("Poteto Mode") but installs into
    # sanitizeName(name) ("poteto-mode"): verify looked for "Poteto Mode" and never found it.
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    _write_display_name_lock(_hermetic)
    for d in (".agents/skills/poteto-mode", ".claude/skills/poteto-mode"):
        (_hermetic / d).mkdir(parents=True)
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
