from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.shell import (
    BashConfig,
    Dotfiles,
    ZshConfig,
    ZshPlugins,
    keep_foreign_rc_files,
)

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]
DOT = REPO_ROOT / "dotfiles"
MARKER = "devboost — managed by chezmoi"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_zsh_plugins_are_brew_formulae_on_macos_only() -> None:
    assert ZshPlugins.families == ("macos",)
    assert ZshPlugins.self_updating is True
    ex = FakeExecutor()
    ZshPlugins().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "zsh-autosuggestions", "zsh-syntax-highlighting"]
    ]


def test_zsh_config_needs_the_dotfiles_and_the_plugins() -> None:
    assert ZshConfig.families == ("macos",)
    assert {Dotfiles, ZshPlugins} <= set(ZshConfig.requires)


def test_zsh_config_verify_reads_the_applied_files(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert ZshConfig().verify(ctx) is False
    frag = home / ".config" / "devboost" / "shell.zsh"
    frag.parent.mkdir(parents=True)
    frag.write_text("# fragment\n", encoding="utf-8")
    (home / ".zshrc").write_text((DOT / "dot_zshrc").read_text(encoding="utf-8"),
                                 encoding="utf-8")
    assert ZshConfig().verify(ctx) is True
    (home / ".zshrc").write_text("export ZSH=$HOME/.oh-my-zsh\n", encoding="utf-8")
    assert ZshConfig().verify(ctx) is False


def test_foreign_rc_files_are_kept_and_managed_ones_left(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    (home / ".zprofile").write_text(f"# {MARKER}\n", encoding="utf-8")
    (home / ".bash_profile").symlink_to(home / "gone")  # a dangling link counts too
    kept = keep_foreign_rc_files(home)
    assert {p.name for p in kept} == {".zshrc.pre-devboost", ".bash_profile.pre-devboost"}
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    # A copy, not a move: the original stays until `chezmoi apply --force` replaces it.
    assert (home / ".zshrc").read_text(encoding="utf-8") == "mine\n"
    # A symlink is kept as the link itself, not followed.
    backup_link = home / ".bash_profile.pre-devboost"
    assert backup_link.is_symlink()
    assert backup_link.readlink() == home / "gone"
    assert (home / ".bash_profile").is_symlink()
    assert (home / ".zprofile").read_text(encoding="utf-8") == f"# {MARKER}\n"
    assert not (home / ".zprofile.pre-devboost").exists()


def test_an_earlier_backup_is_never_overwritten(home: Path) -> None:
    (home / ".zshrc.pre-devboost").write_text("first\n", encoding="utf-8")
    (home / ".zshrc").write_text("second\n", encoding="utf-8")
    assert [p.name for p in keep_foreign_rc_files(home)] == [".zshrc.pre-devboost.1"]
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "first\n"
    assert (home / ".zshrc.pre-devboost.1").read_text(encoding="utf-8") == "second\n"


def test_dotfiles_sets_a_foreign_zshrc_aside_on_macos_before_applying(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    ex = FakeExecutor()
    Dotfiles().install(Ctx(os=MAC, ex=ex))
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    assert any(c[:2] == ["chezmoi", "apply"] for c in ex.calls)


def test_a_failed_apply_leaves_the_original_rc_files_in_place(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    (home / ".zprofile").write_text('eval "$(/opt/homebrew/bin/brew shellenv)"\n',
                                    encoding="utf-8")
    ex = FakeExecutor(scripts={"chezmoi": Result(1)})
    with pytest.raises(InstallError):
        Dotfiles().install(Ctx(os=MAC, ex=ex))
    assert (home / ".zshrc").read_text(encoding="utf-8") == "mine\n"
    assert (home / ".zprofile").read_text(encoding="utf-8") == (
        'eval "$(/opt/homebrew/bin/brew shellenv)"\n'
    )
    assert (home / ".zprofile.pre-devboost").is_file()


def test_dotfiles_leaves_rc_files_alone_on_linux(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    Dotfiles().install(Ctx(os=FEDORA, ex=FakeExecutor()))
    assert (home / ".zshrc").read_text(encoding="utf-8") == "mine\n"
    assert not (home / ".zshrc.pre-devboost").exists()


def test_bash_config_is_linux_only() -> None:
    assert BashConfig.families == ("fedora", "debian", "arch")


def test_terminal_and_shell_install_the_zsh_setup() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    for name in ("terminal", "shell"):
        planned = toposort(expand([name], profiles, modules), modules)
        for want in ("zsh-config", "zsh-plugins", "bash", "dotfiles", "ghostty"):
            assert want in planned, (name, want)
