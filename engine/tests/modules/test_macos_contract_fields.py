from __future__ import annotations

from typing import ClassVar

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64")


class _Delta(PackageModule):
    name: ClassVar[str] = "delta"
    cmd: ClassVar[str] = "delta"
    fedora_pkg: ClassVar[str] = "git-delta"
    brew_pkg: ClassVar[str | None] = "git-delta"


class _Jq(PackageModule):
    name: ClassVar[str] = "jq"
    cmd: ClassVar[str] = "jq"
    fedora_pkg: ClassVar[str] = "jq"


class _CaskTool(PackageModule):
    name: ClassVar[str] = "caskt"
    cmd: ClassVar[str] = "caskt"
    fedora_pkg: ClassVar[str] = "caskt"
    brew_cask: ClassVar[str | None] = "caskt-app"


class _App(FlatpakApp):
    name: ClassVar[str] = "someapp"
    app_id: ClassVar[str] = "org.some.App"
    cask: ClassVar[str | None] = "some-app"


class _NoCaskApp(FlatpakApp):
    name: ClassVar[str] = "nocask"
    app_id: ClassVar[str] = "org.no.Cask"


def test_package_module_uses_brew_pkg_on_macos() -> None:
    ex = FakeExecutor()
    _Delta().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["brew", "install", "--formula", "-y", "git-delta"]


def test_package_module_brew_name_defaults_to_module_name() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1)})  # not installed
    assert _Jq().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--formula", "--versions", "jq"]]


def test_package_module_force_upgrades_when_installed() -> None:
    ex = FakeExecutor()  # brew list → ok (installed)
    _Jq().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--formula", "jq"]


def test_package_module_cask_variant() -> None:
    ex = FakeExecutor()
    _CaskTool().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "caskt-app"]]
    assert _CaskTool().verify(Ctx(os=MAC, ex=FakeExecutor())) is True


def test_flatpak_app_installs_cask_on_macos() -> None:
    ex = FakeExecutor()
    _App().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "some-app"]]


def test_flatpak_app_without_cask_is_unsupported_on_macos() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert _NoCaskApp().verify(ctx) is False
    with pytest.raises(UnsupportedOS, match="nocask"):
        _NoCaskApp().install(ctx)
