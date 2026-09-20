from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.base import Chezmoi
from devboost.modules.editors import Fresh
from devboost.modules.mise import _NOTE_NVM, Mise
from devboost.modules.ripgrep import Ripgrep
from devboost.modules.shell import Starship

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

CASES: list[tuple[type[Module], str]] = [
    (Ripgrep, "ripgrep"),
    (Chezmoi, "chezmoi"),
    (Starship, "starship"),
    (Mise, "mise"),
    (Fresh, "fresh-editor"),
]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_installs_the_formula_on_macos(cls: type[Module], formula: str) -> None:
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    # mise also points itself at `gh` for GitHub tokens (see test_mise_github_token.py);
    # the formula install is still the first thing every one of these does.
    assert ex.calls[0] == ["brew", "install", "--formula", "-y", formula]
    if cls is not Mise:
        assert ex.calls == [["brew", "install", "--formula", "-y", formula]]


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_verifies_through_brew_on_macos(cls: type[Module], formula: str) -> None:
    on_path = {"rg", "chezmoi", "starship", "mise", "fresh"}
    ex = FakeExecutor(scripts={"brew": Result(1)}, present=on_path)
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False  # on PATH is not enough on a Mac
    assert ex.calls == [["brew", "list", "--formula", "--versions", formula]]


def test_fresh_seeds_its_config_on_macos(tmp_path: Path) -> None:
    Fresh().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert (tmp_path / ".config" / "fresh" / "config.json").is_file()


def test_linux_keeps_its_installers_and_stays_supported(tmp_path: Path) -> None:
    ex = FakeExecutor()
    Chezmoi().install(Ctx(os=FEDORA, ex=ex))
    assert any("get.chezmoi.io" in " ".join(c) for c in ex.calls)
    names = [cls.name for cls, _ in CASES]
    plan = build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "none")
    assert all(p.skip_reason is None for p in plan), plan


def _seed_nvm_and_sdkman(tmp_path: Path) -> None:
    (tmp_path / ".nvm" / "alias").mkdir(parents=True)
    (tmp_path / ".nvm" / "alias" / "default").write_text("v22.1.0\n", encoding="utf-8")
    nvm_block = "# BEGIN NVM\nexport NVM_DIR=$HOME/.nvm\n# END NVM\n"
    (tmp_path / ".zshrc.local").write_text(nvm_block, encoding="utf-8")
    # bash_profile.local is the third rc file the macOS migration touches (mise.py
    # _RC_FILES["macos"]) — seed it too so the migration is proven against all three,
    # not just .zshrc.local / .zprofile.local.
    (tmp_path / ".bash_profile.local").write_text(nvm_block, encoding="utf-8")
    java_dir = tmp_path / ".sdkman" / "candidates" / "java" / "21.0.1-tem"
    java_dir.mkdir(parents=True)
    (tmp_path / ".sdkman" / "candidates" / "java" / "current").symlink_to(java_dir)
    (tmp_path / ".zprofile.local").write_text(
        "# BEGIN SDKMAN\nexport SDKMAN_DIR=$HOME/.sdkman\n# END SDKMAN\n", encoding="utf-8"
    )


def test_mise_migrates_nvm_and_sdkman_on_macos(tmp_path: Path) -> None:
    """After brew installs mise, the same nvm/sdkman migration Linux does runs on a Mac
    (ruling R2) — but against the zsh-local rc files M2 leaves to the user, never the
    chezmoi-managed ~/.zshrc / ~/.zprofile or the Linux-only ~/.bashrc."""
    _seed_nvm_and_sdkman(tmp_path)
    ex = FakeExecutor()
    Mise().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "install", "--formula", "-y", "mise"] in ex.calls
    assert ["mise", "use", "-g", "node@22.1.0"] in ex.calls
    assert ["mise", "use", "-g", "java@21.0.1-tem"] in ex.calls

    zshrc_local = (tmp_path / ".zshrc.local").read_text(encoding="utf-8")
    assert "# export NVM_DIR=$HOME/.nvm" in zshrc_local
    assert "migrated nvm init to mise" in zshrc_local

    bash_profile_local = (tmp_path / ".bash_profile.local").read_text(encoding="utf-8")
    assert "# export NVM_DIR=$HOME/.nvm" in bash_profile_local
    assert "migrated nvm init to mise" in bash_profile_local

    zprofile_local = (tmp_path / ".zprofile.local").read_text(encoding="utf-8")
    assert "# export SDKMAN_DIR=$HOME/.sdkman" in zprofile_local
    assert "migrated sdkman init to mise" in zprofile_local

    assert not (tmp_path / ".bashrc").exists()  # mac never touches the Linux rc file


def test_mise_migration_is_idempotent_under_force_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-R17: an --update re-run (force=True) must not re-comment the block or prompt."""
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    _seed_nvm_and_sdkman(tmp_path)
    ex = FakeExecutor()
    ctx = Ctx(os=MAC, ex=ex, force=True)

    Mise().install(ctx)
    Mise().install(ctx)

    zshrc_local = (tmp_path / ".zshrc.local").read_text(encoding="utf-8")
    assert zshrc_local.count("migrated nvm init to mise") == 1
    assert zshrc_local.count("# export NVM_DIR=$HOME/.nvm") == 1
    bash_profile_local = (tmp_path / ".bash_profile.local").read_text(encoding="utf-8")
    assert bash_profile_local.count("migrated nvm init to mise") == 1
    zprofile_local = (tmp_path / ".zprofile.local").read_text(encoding="utf-8")
    assert zprofile_local.count("migrated sdkman init to mise") == 1

    # `mise use -g` re-runs identically each pass — the mise CLI itself is idempotent
    # (same pin written again), so two identical calls are not a "duplicate side effect"
    # beyond that; nothing about the call shape changes between the two install()s.
    use_calls = [c for c in ex.calls if c[:2] == ["mise", "use"]]
    want = [["mise", "use", "-g", "node@22.1.0"], ["mise", "use", "-g", "java@21.0.1-tem"]]
    assert use_calls == want * 2
    assert all(c and c[0] != "sudo" for c in ex.calls)  # never prompts unattended


def test_mise_migration_backs_up_each_rc_file_once(tmp_path: Path) -> None:
    """Before the first rewrite, each rc file is copied to <name>.pre-devboost — a
    crash mid-write must never be able to truncate the user's own rc with no copy."""
    _seed_nvm_and_sdkman(tmp_path)
    original_zshrc_local = (tmp_path / ".zshrc.local").read_text(encoding="utf-8")
    Mise().install(Ctx(os=MAC, ex=FakeExecutor()))

    backup = tmp_path / ".zshrc.local.pre-devboost"
    assert backup.read_text(encoding="utf-8") == original_zshrc_local

    # A later, unrelated edit to the live file must not touch the one-shot backup —
    # it is taken once, the first time this rc file is ever rewritten.
    (tmp_path / ".zshrc.local").write_text("# something else entirely\n", encoding="utf-8")
    Mise()._comment_out(Ctx(os=MAC, ex=FakeExecutor()), "# BEGIN NVM", "# END NVM", _NOTE_NVM)
    assert backup.read_text(encoding="utf-8") == original_zshrc_local


def test_mise_migration_tolerates_non_utf8_bytes_in_an_rc_file(tmp_path: Path) -> None:
    """A stray non-UTF-8 byte in a user-owned rc file must not crash the migration (and
    block mise, and everything that requires it) — errors="replace" degrades gracefully."""
    (tmp_path / ".nvm" / "alias").mkdir(parents=True)
    (tmp_path / ".nvm" / "alias" / "default").write_text("v22.1.0\n", encoding="utf-8")
    (tmp_path / ".zshrc.local").write_bytes(
        b"# BEGIN NVM\nexport NVM_DIR=$HOME/.nvm  # \xff stray byte\n# END NVM\n"
    )
    Mise().install(Ctx(os=MAC, ex=FakeExecutor()))  # no UnicodeDecodeError
    text = (tmp_path / ".zshrc.local").read_text(encoding="utf-8", errors="replace")
    assert "migrated nvm init to mise" in text
