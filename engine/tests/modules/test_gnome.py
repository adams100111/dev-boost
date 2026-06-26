from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.gnome import (
    _FUNCTIONAL_UUIDS,
    GnomeExtensions,
    GnomeManagerApps,
    GnomeSettings,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_all_gnome_modules_are_gui() -> None:
    assert GnomeSettings.gui and GnomeExtensions.gui and GnomeManagerApps.gui


def test_gnome_settings_loads_dconf_dump() -> None:
    ctx = _ctx()
    GnomeSettings().install(ctx)
    assert ["dconf", "load", "/"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_gnome_settings_verify_prefers_dark() -> None:
    ctx = _ctx(scripts={"gsettings": Result(0, stdout="'prefer-dark'")})
    assert GnomeSettings().verify(ctx) is True


def test_gnome_extensions_installs_and_enables_each() -> None:
    ctx = _ctx()
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    for uuid in _FUNCTIONAL_UUIDS:
        assert ["gext", "install", uuid] in calls
        assert ["gext", "enable", uuid] in calls


def test_gnome_manager_apps_install() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="")})
    GnomeManagerApps().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "gnome-extensions-app", "gnome-tweaks"] in calls
    assert ["flatpak", "install", "-y", "flathub", "com.mattjakeman.ExtensionManager"] in calls
