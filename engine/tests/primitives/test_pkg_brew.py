from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, PresentUnmanaged, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import BrewTap, Ctx, DnfRepo

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
