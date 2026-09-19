from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import devboost.modules.shell as shell_mod
from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.shell import (
    _TAKEN_OVER_LINUX,
    BashConfig,
    Dotfiles,
    ZshConfig,
    ZshPlugins,
    back_up_rc_files,
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


def test_zsh_config_verify_needs_the_source_line_not_just_the_marker(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    frag = home / ".config" / "devboost" / "shell.zsh"
    frag.parent.mkdir(parents=True)
    frag.write_text("# fragment\n", encoding="utf-8")
    (home / ".zshrc").write_text(f"# {MARKER}\nexport EDITOR=vi\n", encoding="utf-8")
    assert ZshConfig().verify(ctx) is False


def test_zsh_config_verify_tolerates_a_non_utf8_zshrc(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    frag = home / ".config" / "devboost" / "shell.zsh"
    frag.parent.mkdir(parents=True)
    frag.write_text("# fragment\n", encoding="utf-8")
    (home / ".zshrc").write_bytes("# caf\u00e9 \u2014 mine\nalias ll='ls -l'\n".encode("latin-1",
                                                                              "replace"))
    assert ZshConfig().verify(ctx) is False


def test_foreign_rc_files_are_kept_and_managed_ones_left(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    (home / ".zprofile").write_bytes((DOT / "dot_zprofile").read_bytes())  # managed, as applied
    (home / ".bash_profile").symlink_to(home / "gone")  # a dangling link counts too
    kept = back_up_rc_files(home, DOT)
    assert {p.name for p in kept} == {".zshrc.pre-devboost", ".bash_profile.pre-devboost"}
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    # A copy, not a move: the original stays until `chezmoi apply --force` replaces it.
    assert (home / ".zshrc").read_text(encoding="utf-8") == "mine\n"
    # A symlink is kept as the link itself, not followed.
    backup_link = home / ".bash_profile.pre-devboost"
    assert backup_link.is_symlink()
    assert backup_link.readlink() == home / "gone"
    assert (home / ".bash_profile").is_symlink()
    assert (home / ".zprofile").read_bytes() == (DOT / "dot_zprofile").read_bytes()
    assert not (home / ".zprofile.pre-devboost").exists()


def test_an_earlier_backup_is_never_overwritten(home: Path) -> None:
    (home / ".zshrc.pre-devboost").write_text("first\n", encoding="utf-8")
    (home / ".zshrc").write_text("second\n", encoding="utf-8")
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost.1"]
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "first\n"
    assert (home / ".zshrc.pre-devboost.1").read_text(encoding="utf-8") == "second\n"


def test_a_managed_rc_file_with_appended_lines_is_backed_up(home: Path) -> None:
    # Another tool (an installer, `conda init`, …) appended to the managed ~/.zshrc; the
    # next `chezmoi apply --force` would drop that line, so it is kept first.
    drifted = (DOT / "dot_zshrc").read_bytes() + b'export PATH="$HOME/.tool/bin:$PATH"\n'
    (home / ".zshrc").write_bytes(drifted)
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost"]
    assert (home / ".zshrc.pre-devboost").read_bytes() == drifted


def test_an_unchanged_managed_rc_file_gets_no_backup(home: Path) -> None:
    for name, src in ((".zshrc", "dot_zshrc"), (".zprofile", "dot_zprofile"),
                      (".bash_profile", "dot_bash_profile")):
        (home / name).write_bytes((DOT / src).read_bytes())
    assert back_up_rc_files(home, DOT) == []
    assert not list(home.glob("*.pre-devboost*"))


def test_a_retry_makes_no_identical_backup(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost"]
    assert back_up_rc_files(home, DOT) == []  # e.g. the apply failed and the run is retried
    assert sorted(p.name for p in home.glob(".zshrc.pre-devboost*")) == [".zshrc.pre-devboost"]
    (home / ".zshrc").write_text("mine, edited\n", encoding="utf-8")
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost.1"]
    assert back_up_rc_files(home, DOT) == []  # compared with the NEWEST backup


def test_a_retry_with_the_same_symlink_makes_no_new_backup(home: Path) -> None:
    (home / "dotrepo").mkdir()
    (home / "dotrepo" / "zshrc").write_text("mine\n", encoding="utf-8")
    (home / ".zshrc").symlink_to(home / "dotrepo" / "zshrc")
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost"]
    assert (home / ".zshrc.pre-devboost").readlink() == home / "dotrepo" / "zshrc"
    assert back_up_rc_files(home, DOT) == []
    # Same bytes behind a different link target is still a different file to keep.
    (home / "dotrepo" / "zshrc2").write_text("mine\n", encoding="utf-8")
    (home / ".zshrc").unlink()
    (home / ".zshrc").symlink_to(home / "dotrepo" / "zshrc2")
    assert [p.name for p in back_up_rc_files(home, DOT)] == [".zshrc.pre-devboost.1"]


def test_backup_log_names_the_matching_local_file(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(log, "ok", seen.append)
    for name in (".zshrc", ".zprofile", ".bash_profile"):
        (home / name).write_text("mine\n", encoding="utf-8")
    Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor()))
    by_file = {n: [m for m in seen if f"~/{n} as" in m] for n in (".zshrc", ".zprofile",
                                                                  ".bash_profile")}
    for name, msgs in by_file.items():
        assert len(msgs) == 1, (name, seen)
        assert f"~/{name}.local" in msgs[0]
        others = {".zshrc", ".zprofile", ".bash_profile"} - {name}
        assert not any(f"~/{o}.local" in msgs[0] for o in others), msgs[0]


def _digests_file(home: Path) -> Path:
    return home / ".local" / "state" / "devboost" / "rc-digests.json"


def _new_release(tmp_path: Path) -> Path:
    """A copy of dotfiles/ whose rc sources changed since the user's last apply."""
    src = tmp_path / "release-src"
    src.mkdir()
    for name in ("dot_zshrc", "dot_zprofile", "dot_bash_profile"):
        shutil.copy(DOT / name, src / name)
        with (src / name).open("a", encoding="utf-8") as f:
            f.write("# a newer release added this line\n")
    return src


def test_apply_records_the_rc_file_digests(home: Path) -> None:
    for name, src in ((".zshrc", "dot_zshrc"), (".zprofile", "dot_zprofile")):
        (home / name).write_bytes((DOT / src).read_bytes())  # as chezmoi would write them
    (home / ".bash_profile").write_text("mine\n", encoding="utf-8")  # foreign: not recorded
    Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor()))
    state = _digests_file(home)
    assert json.loads(state.read_text(encoding="utf-8")) == {
        name: hashlib.sha256((DOT / src).read_bytes()).hexdigest()
        for name, src in ((".zshrc", "dot_zshrc"), (".zprofile", "dot_zprofile"))
    }
    assert (state.parent.stat().st_mode & 0o777) == 0o700


def test_a_failed_apply_records_no_digests(home: Path) -> None:
    (home / ".zshrc").write_bytes((DOT / "dot_zshrc").read_bytes())
    with pytest.raises(InstallError):
        Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor(scripts={"chezmoi": Result(1)})))
    assert not _digests_file(home).exists()


def test_a_digest_bookkeeping_error_warns_but_does_not_fail_install(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """record_rc_digests is bookkeeping only (M-R26): a PermissionError on the state dir
    (mkdir/mkstemp/read_bytes) must log a warning, never fail an otherwise successful
    dotfiles install (C-R16)."""

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("[Errno 13] Permission denied: rc-digests state dir")

    monkeypatch.setattr(shell_mod, "record_rc_digests", _raise)
    warnings: list[str] = []
    monkeypatch.setattr(log, "warn", warnings.append)
    (home / ".zshrc").write_bytes((DOT / "dot_zshrc").read_bytes())

    Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor()))  # must not raise

    assert any("rc digest" in w for w in warnings)
    assert Dotfiles()._stamp().is_file()  # install still ran to completion


def test_an_untouched_file_from_an_older_release_gets_no_backup(
    home: Path, tmp_path: Path
) -> None:
    for name, src in ((".zshrc", "dot_zshrc"), (".zprofile", "dot_zprofile"),
                      (".bash_profile", "dot_bash_profile")):
        (home / name).write_bytes((DOT / src).read_bytes())
    Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor()))  # records what the apply wrote
    assert back_up_rc_files(home, _new_release(tmp_path)) == []


def test_a_user_appended_line_is_backed_up_despite_the_recorded_digest(
    home: Path, tmp_path: Path
) -> None:
    (home / ".zshrc").write_bytes((DOT / "dot_zshrc").read_bytes())
    Dotfiles().install(Ctx(os=MAC, ex=FakeExecutor()))
    with (home / ".zshrc").open("a", encoding="utf-8") as f:
        f.write('export PATH="$HOME/.tool/bin:$PATH"\n')
    assert [p.name for p in back_up_rc_files(home, _new_release(tmp_path))] == [
        ".zshrc.pre-devboost"
    ]


@pytest.mark.parametrize("junk", ["{not json", "[1, 2]", '{".zshrc": 5}', ""])
def test_a_corrupt_digest_file_falls_back_to_the_source_comparison(
    home: Path, tmp_path: Path, junk: str
) -> None:
    (home / ".zshrc").write_bytes((DOT / "dot_zshrc").read_bytes())
    state = _digests_file(home)
    state.parent.mkdir(parents=True)
    state.write_text(junk, encoding="utf-8")
    assert back_up_rc_files(home, DOT) == []  # equals the source: still no backup
    # Outdated vs a newer source, and no usable digest: backed up (today's behaviour).
    assert [p.name for p in back_up_rc_files(home, _new_release(tmp_path))] == [
        ".zshrc.pre-devboost"
    ]


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


def test_bashrc_foreign_is_backed_up_on_linux(home: Path) -> None:
    (home / ".bashrc").write_text("mine\n", encoding="utf-8")
    kept = back_up_rc_files(home, DOT, _TAKEN_OVER_LINUX)
    assert [p.name for p in kept] == [".bashrc.pre-devboost"]
    assert (home / ".bashrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    # A copy, not a move: the original stays until `chezmoi apply --force` replaces it.
    assert (home / ".bashrc").read_text(encoding="utf-8") == "mine\n"


def test_bashrc_drifted_is_backed_up_on_linux(home: Path) -> None:
    # Managed, but another tool appended a line the next `apply --force` would drop.
    drifted = (DOT / "dot_bashrc").read_bytes() + b'export PATH="$HOME/.tool/bin:$PATH"\n'
    (home / ".bashrc").write_bytes(drifted)
    kept = back_up_rc_files(home, DOT, _TAKEN_OVER_LINUX)
    assert [p.name for p in kept] == [".bashrc.pre-devboost"]
    assert (home / ".bashrc.pre-devboost").read_bytes() == drifted


def test_bashrc_unchanged_gets_no_backup_on_linux(home: Path) -> None:
    (home / ".bashrc").write_bytes((DOT / "dot_bashrc").read_bytes())
    assert back_up_rc_files(home, DOT, _TAKEN_OVER_LINUX) == []
    assert not list(home.glob(".bashrc.pre-devboost*"))


def test_dotfiles_backs_up_a_foreign_bashrc_on_linux_before_applying(home: Path) -> None:
    (home / ".bashrc").write_text("mine\n", encoding="utf-8")
    ex = FakeExecutor()
    Dotfiles().install(Ctx(os=FEDORA, ex=ex))
    assert (home / ".bashrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    assert any(c[:2] == ["chezmoi", "apply"] for c in ex.calls)


def test_dotfiles_records_the_bashrc_digest_on_linux(home: Path) -> None:
    (home / ".bashrc").write_bytes((DOT / "dot_bashrc").read_bytes())
    Dotfiles().install(Ctx(os=FEDORA, ex=FakeExecutor()))
    state = _digests_file(home)
    assert json.loads(state.read_text(encoding="utf-8")) == {
        ".bashrc": hashlib.sha256((DOT / "dot_bashrc").read_bytes()).hexdigest()
    }


def test_dotfiles_leaves_bashrc_alone_on_omarchy(home: Path) -> None:
    """Omarchy owns ~/.bashrc itself (`.chezmoiignore` skips it) and dev-boost only sources
    a fragment from it (bash-config) — apply never touches it, so there's nothing to back
    up or record a digest for."""
    omarchy = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
    (home / ".bashrc").write_text("mine\n", encoding="utf-8")
    Dotfiles().install(Ctx(os=omarchy, ex=FakeExecutor()))
    assert (home / ".bashrc").read_text(encoding="utf-8") == "mine\n"
    assert not (home / ".bashrc.pre-devboost").exists()
    assert not _digests_file(home).exists()


def test_bash_config_is_linux_only() -> None:
    assert BashConfig.families == ("fedora", "debian", "arch")


def test_terminal_and_shell_install_the_zsh_setup() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    for name in ("terminal", "shell"):
        planned = toposort(expand([name], profiles, modules), modules)
        for want in ("zsh-config", "zsh-plugins", "bash", "dotfiles", "ghostty"):
            assert want in planned, (name, want)
