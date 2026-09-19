from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser, PresentUnmanaged, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import BrewTap, Ctx, DnfRepo
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


@dataclass
class _EnvRecorder(FakeExecutor):
    """FakeExecutor that also records the env passed to each call."""

    envs: list[dict[str, str]] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        self.envs.append(dict(env or {}))
        return super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive,
            timeout=timeout,
        )


def test_manager_for_macos_is_brew() -> None:
    assert isinstance(pkg.manager_for(MAC), pkg.Brew)


def test_install_formula_argv_env_and_never_sudo() -> None:
    ex = _EnvRecorder()
    pkg.install(Ctx(os=MAC, ex=ex), "git", "jq")
    assert ex.calls == [["brew", "install", "--formula", "-y", "git", "jq"]]
    assert ex.envs[0] == pkg.BREW_ENV


def test_install_formula_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1, stderr="No available formula")})
    with pytest.raises(InstallError):
        pkg.install(Ctx(os=MAC, ex=ex), "nope")


def test_install_cask_uses_adopt() -> None:
    ex = FakeExecutor()
    pkg.install_cask(Ctx(os=MAC, ex=ex), "ghostty")
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "ghostty"]]


def test_install_cask_hand_installed_app_is_present_unmanaged() -> None:
    # Homebrew 7.0.4 cask/artifact/moved.rb: the --adopt path raises this when the
    # existing app's bundle version differs from the one being installed.
    err = "Error: It seems the existing App is different from the one being installed."
    ex = FakeExecutor(scripts={"brew": Result(1, stderr=err)})
    with pytest.raises(PresentUnmanaged):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "visual-studio-code")


def test_install_cask_already_an_app_fallback_is_present_unmanaged() -> None:
    # Wording without --adopt/--force; kept as a fallback in case brew's flow changes.
    err = "Error: It seems there is already an App at '/Applications/Visual Studio Code.app'."
    ex = FakeExecutor(scripts={"brew": Result(1, stderr=err)})
    with pytest.raises(PresentUnmanaged):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "visual-studio-code")


def test_install_cask_other_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1, stderr="Download failed")})
    with pytest.raises(InstallError):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "ghostty")


def test_installed_and_cask_installed_query_brew_list() -> None:
    ex = FakeExecutor()
    ctx = Ctx(os=MAC, ex=ex)
    assert pkg.installed(ctx, "git") is True
    assert pkg.cask_installed(ctx, "ghostty") is True
    assert ex.calls == [
        ["brew", "list", "--formula", "--versions", "git"],
        ["brew", "list", "--cask", "--versions", "ghostty"],
    ]
    missing = Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)}))
    assert pkg.installed(missing, "git") is False


def test_upgrade_formula() -> None:
    ex = FakeExecutor()
    pkg.upgrade(Ctx(os=MAC, ex=ex), "git")
    assert ex.calls == [["brew", "upgrade", "--formula", "git"]]


def test_brew_tap_source_taps_then_installs() -> None:
    ex = FakeExecutor()
    src: pkg.Source = OsMap[pkg.Repo](macos=BrewTap("ddev/ddev"))
    pkg.install(Ctx(os=MAC, ex=ex), "ddev/ddev/ddev", source=src)
    assert ex.calls == [
        ["brew", "tap", "ddev/ddev"],
        ["brew", "install", "--formula", "-y", "ddev/ddev/ddev"],
    ]


def test_brew_tap_with_url() -> None:
    ex = FakeExecutor()
    pkg.Brew().add_repo(Ctx(os=MAC, ex=ex), BrewTap("me/tap", "https://example.com/tap.git"))
    assert ex.calls == [["brew", "tap", "me/tap", "https://example.com/tap.git"]]


def test_brew_rejects_dnf_repo() -> None:
    with pytest.raises(TypeError):
        pkg.Brew().add_repo(Ctx(os=MAC, ex=FakeExecutor()), DnfRepo("x", "https://x"))


def test_cask_helpers_are_macos_only() -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    with pytest.raises(UnsupportedOS):
        pkg.install_cask(ctx, "ghostty")
    with pytest.raises(UnsupportedOS):
        pkg.upgrade(ctx, "git")
    assert pkg.cask_installed(ctx, "ghostty") is False


def test_refresh_index_runs_brew_update_once_on_macos() -> None:
    ex = _EnvRecorder()
    pkg.refresh_index(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "update"]]
    assert ex.envs == [pkg.BREW_ENV]


def test_refresh_index_failure_is_not_raised_on_macos() -> None:
    pkg.refresh_index(Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)})))


# --- M3 AF2: adopting a hand-installed app needs sudo -----------------------------------

_SUDO_ERR = (
    "sudo: a terminal is required to read the password; either use the -S option to read"
    " from standard input or configure an askpass helper\nsudo: a password is required\n"
    "Error: Failure while executing; `/usr/bin/sudo -E -- /bin/chmod -R a+rX,go-w "
    "/Applications/Obsidian.app` exited with 1."
)
_ADOPT = ["brew", "install", "--cask", "-y", "--adopt", "obsidian"]


def _cask_info(app: Path) -> Result:
    art = [{"app": ["Obsidian.app"], "target": str(app)}, {"zap": [{"trash": ["~/x"]}]}]
    return Result(0, stdout=json.dumps({"casks": [{"token": "obsidian", "artifacts": art}]}))


def _brew_ex(app: Path, *, listed: bool = False, install: Result | None = None) -> Scripted:
    return Scripted(
        answers={
            ("brew", "list", "--cask", "--versions", "obsidian"): Result(0 if listed else 1),
            ("brew", "info", "--json=v2", "--cask", "obsidian"): _cask_info(app),
            tuple(_ADOPT): install or Result(0),
        }
    )


def test_no_sudo_hand_installed_app_is_left_untouched_before_brew_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    app = tmp_path / "Applications" / "Obsidian.app"
    app.mkdir(parents=True)
    ex = _brew_ex(app)
    with pytest.raises(PresentUnmanaged, match="obsidian"):
        pkg.install_cask(Ctx(os=MAC, ex=ex, no_sudo=True), "obsidian")
    assert _ADOPT not in ex.calls  # never attempted


def test_no_sudo_missing_app_is_installed_normally(tmp_path: Path) -> None:
    ex = _brew_ex(tmp_path / "Applications" / "Obsidian.app")
    pkg.install_cask(Ctx(os=MAC, ex=ex, no_sudo=True), "obsidian")
    assert _ADOPT in ex.calls


def test_with_sudo_the_hand_installed_app_is_adopted(tmp_path: Path) -> None:
    app = tmp_path / "Applications" / "Obsidian.app"
    app.mkdir(parents=True)
    ex = _brew_ex(app)
    pkg.install_cask(Ctx(os=MAC, ex=ex, no_sudo=False), "obsidian")
    assert _ADOPT in ex.calls


def test_adopt_refused_by_sudo_with_the_bundle_present_is_present_unmanaged(
    tmp_path: Path,
) -> None:
    # Fallback (a): the pre-check did not catch it (e.g. brew info unavailable, or sudo was
    # granted but expired), brew's own sudo step failed on the existing bundle.
    app = tmp_path / "Applications" / "Obsidian.app"
    app.mkdir(parents=True)
    ex = _brew_ex(app, install=Result(1, stdout="==> Adopting existing App", stderr=_SUDO_ERR))
    with pytest.raises(PresentUnmanaged):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "obsidian")


def test_sudo_refused_without_a_bundle_needs_the_user(tmp_path: Path) -> None:
    ex = _brew_ex(tmp_path / "missing.app", install=Result(1, stderr=_SUDO_ERR))
    with pytest.raises(NeedsUser, match="needs your password"):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "obsidian")


def test_cask_app_paths_reads_targets_and_bare_app_names() -> None:
    arts = [{"app": ["Foo.app"]}, {"app": ["X.app"], "target": "/Applications/Y.app"}, "junk"]
    info = Result(0, stdout=json.dumps({"casks": [{"artifacts": arts}]}))
    ex = Scripted(answers={("brew", "info"): info})
    assert pkg.Brew().cask_app_paths(Ctx(os=MAC, ex=ex), "foo") == [
        Path("/Applications/Foo.app"),
        Path("/Applications/Y.app"),
    ]
    bad = Scripted(answers={("brew", "info"): Result(0, stdout="not json")})
    assert pkg.Brew().cask_app_paths(Ctx(os=MAC, ex=bad), "foo") == []
