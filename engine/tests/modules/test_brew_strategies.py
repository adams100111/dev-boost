from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules._pkgmodule import PackageModule

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Listed(FakeExecutor):
    """`brew list …` succeeds only for names in ``installed``; every other call is ok."""

    def __init__(self, installed: set[str]) -> None:
        super().__init__()
        self.installed = installed

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:2]) == ["brew", "list"]:
            # Like brew 7.0.4: `list` finds Caskroom/<token> or Cellar/<token> only, so a
            # tap-qualified name is never listed.
            name = argv[-1]
            return Result(0) if "/" not in name and name in self.installed else Result(1)
        return Result(0)


def test_formula_installs_every_formula_in_one_call() -> None:
    ex = FakeExecutor()
    BrewFormula("zsh-autosuggestions", "zsh-syntax-highlighting").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "zsh-autosuggestions", "zsh-syntax-highlighting"]
    ]


def test_formula_verify_needs_every_formula() -> None:
    assert BrewFormula("a", "b").verify(Ctx(os=MAC, ex=_Listed({"a", "b"}))) is True
    assert BrewFormula("a", "b").verify(Ctx(os=MAC, ex=_Listed({"a"}))) is False


def test_tap_qualified_formula_and_cask_verify_by_token() -> None:
    """C2: presence of `user/tap/token` is probed as `token`."""
    ex = _Listed({"ddev", "aerospace"})
    assert BrewFormula("ddev/ddev/ddev").verify(Ctx(os=MAC, ex=ex)) is True
    assert BrewCask("nikitabobko/tap/aerospace").verify(Ctx(os=MAC, ex=ex)) is True
    assert ["brew", "list", "--formula", "--versions", "ddev"] in ex.calls
    assert ["brew", "list", "--cask", "--versions", "aerospace"] in ex.calls
    ex = _Listed({"ddev"})
    BrewFormula("ddev/ddev/ddev").install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--formula", "ddev/ddev/ddev"]


def test_formula_update_upgrades_present_and_installs_missing() -> None:
    ex = _Listed({"a"})
    BrewFormula("a", "b").install(Ctx(os=MAC, ex=ex, force=True))
    assert ["brew", "upgrade", "--formula", "a"] in ex.calls
    assert ex.calls[-1] == ["brew", "install", "--formula", "-y", "b"]


def test_formula_needs_a_name() -> None:
    with pytest.raises(ValueError, match="at least one"):
        BrewFormula()


def test_formula_is_macos_only() -> None:
    # Off macOS a formula name would reach dnf/apt/pacman — refuse, like BrewCask does.
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        BrewFormula("x").install(Ctx(os=FEDORA, ex=ex))
    with pytest.raises(UnsupportedOS):
        BrewFormula("x").install(Ctx(os=FEDORA, ex=ex, force=True))
    assert BrewFormula("x").verify(Ctx(os=FEDORA, ex=ex)) is False
    assert ex.calls == []


def test_cask_is_macos_only() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        BrewCask("x").install(Ctx(os=FEDORA, ex=ex))
    assert BrewCask("x").verify(Ctx(os=FEDORA, ex=ex)) is False
    assert ex.calls == []


def test_formula_equality_is_by_names() -> None:
    assert BrewFormula("x") == BrewFormula("x")
    assert BrewFormula("x") != BrewFormula("y")


def test_cask_installs_with_adopt_and_verifies_the_cask() -> None:
    ex = FakeExecutor()
    BrewCask("ghostty").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "ghostty"]]
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert BrewCask("ghostty").verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--cask", "--versions", "ghostty"]]


def test_strategies_are_installers() -> None:
    assert isinstance(BrewFormula("x"), Installer)
    assert isinstance(BrewCask("x"), Installer)


class _WithMacStrategy(Module):
    name: ClassVar[str] = "with-mac-strategy"
    per_os = OsMap(macos=BrewFormula("thing"))


def test_os_strategy_only_on_the_declared_os() -> None:
    mod = _WithMacStrategy()
    assert mod.os_strategy(Ctx(os=MAC, ex=FakeExecutor())) == BrewFormula("thing")
    assert mod.os_strategy(Ctx(os=FEDORA, ex=FakeExecutor())) is None


class _CustomLinux(PackageModule):
    name: ClassVar[str] = "customlinux"
    cmd: ClassVar[str] = "cl"
    fedora_pkg: ClassVar[str] = "cl"

    def install_linux(self, ctx: Ctx) -> None:
        ctx.ex.run(["sh", "-c", "custom-installer"])

    def verify_linux(self, ctx: Ctx) -> bool:
        return ctx.ex.which("cl-alt")


def test_hooked_package_module_keeps_brew_on_macos() -> None:
    ex = FakeExecutor()
    _CustomLinux().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "customlinux"]]


def test_hooked_package_module_runs_its_hooks_on_linux() -> None:
    ex = FakeExecutor(present={"cl-alt"})
    ctx = Ctx(os=FEDORA, ex=ex)
    _CustomLinux().install(ctx)
    assert ex.calls == [["sh", "-c", "custom-installer"]]
    assert _CustomLinux().verify(ctx) is True


def test_hooked_subclass_keeps_the_base_install_and_verify() -> None:
    # The macOS contract test reads exactly this to decide "brew-backed".
    assert _CustomLinux.install is PackageModule.install
    assert _CustomLinux.verify is PackageModule.verify
