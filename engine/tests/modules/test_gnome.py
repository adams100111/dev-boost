from __future__ import annotations

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import Flatpak as FlatpakModule
from devboost.modules.gnome import (
    _FUNCTIONAL_UUIDS,
    GnomeAestheticsBundle,
    GnomeExtensions,
    GnomeManagerApps,
    GnomeSettings,
    GnomeThemeBundle,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _ubuntu_ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fedora baseline (existing)
# ---------------------------------------------------------------------------


def test_all_gnome_modules_are_gui() -> None:
    assert GnomeSettings.gui and GnomeExtensions.gui and GnomeManagerApps.gui


def test_gnome_manager_apps_requires_flatpak_module() -> None:
    assert FlatpakModule in GnomeManagerApps.requires


def test_gnome_settings_loads_dconf_dump_with_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    ctx = _ctx()
    GnomeSettings().install(ctx)
    assert ["dconf", "load", "/"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_gnome_settings_dconf_headless_uses_dbus_run_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    ctx = _ctx()
    GnomeSettings().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["dbus-run-session", "--", "dconf", "load", "/"] in calls


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


# ---------------------------------------------------------------------------
# Ubuntu — GnomeSettings (dconf/dbus is cross-distro)
# ---------------------------------------------------------------------------


def test_gnome_settings_works_on_ubuntu_with_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    ctx = _ubuntu_ctx()
    GnomeSettings().install(ctx)
    assert ["dconf", "load", "/"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_gnome_settings_headless_dbus_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    ctx = _ubuntu_ctx()
    GnomeSettings().install(ctx)
    assert ["dbus-run-session", "--", "dconf", "load", "/"] in ctx.ex.calls  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Ubuntu — GnomeExtensions
# ---------------------------------------------------------------------------


def test_gnome_extensions_installs_via_pip_on_ubuntu() -> None:
    """When gext is missing on Ubuntu, install via pip3 (no apt package for gext)."""
    ctx = _ubuntu_ctx()  # gext not present → which("gext") returns False
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["pip3", "install", "--user", "gnome-extensions-cli"] in calls
    # No Fedora rpm package must be used
    assert not any("python3-gnome-extensions-cli" in " ".join(c) for c in calls)


def test_gnome_extensions_installs_python3_pip_if_missing_on_ubuntu() -> None:
    """If pip3 itself is absent, install python3-pip via apt first."""
    ctx = _ubuntu_ctx()  # pip3 not present either
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "python3-pip"] in calls
    assert ["pip3", "install", "--user", "gnome-extensions-cli"] in calls


def test_gnome_extensions_skips_pip_when_pip3_present_on_ubuntu() -> None:
    """If pip3 is already on PATH, skip the python3-pip apt install."""
    ctx = _ubuntu_ctx(present={"pip3"})
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("python3-pip" in " ".join(c) for c in calls)
    assert ["pip3", "install", "--user", "gnome-extensions-cli"] in calls


def test_gnome_extensions_skips_gext_install_when_present_on_ubuntu() -> None:
    """If gext is already present, skip all install steps and go straight to enable."""
    ctx = _ubuntu_ctx(present={"gext"})
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("pip3" in " ".join(c) for c in calls)
    assert not any("apt-get" in " ".join(c) for c in calls)
    for uuid in _FUNCTIONAL_UUIDS:
        assert ["gext", "install", uuid] in calls


def test_gnome_extensions_enables_all_uuids_on_ubuntu() -> None:
    ctx = _ubuntu_ctx(present={"gext"})
    GnomeExtensions().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    for uuid in _FUNCTIONAL_UUIDS:
        assert ["gext", "enable", uuid] in calls


# ---------------------------------------------------------------------------
# Ubuntu — GnomeManagerApps
# ---------------------------------------------------------------------------


def test_gnome_manager_apps_installs_only_tweaks_on_ubuntu() -> None:
    """gnome-extensions-app has no apt package; only gnome-tweaks is installed."""
    ctx = _ubuntu_ctx(scripts={"flatpak": Result(0, stdout="")})
    GnomeManagerApps().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "gnome-tweaks"] in calls
    assert not any("gnome-extensions-app" in " ".join(c) for c in calls)


def test_gnome_manager_apps_installs_extension_manager_flatpak_on_ubuntu() -> None:
    ctx = _ubuntu_ctx(scripts={"flatpak": Result(0, stdout="")})
    GnomeManagerApps().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["flatpak", "install", "-y", "flathub", "com.mattjakeman.ExtensionManager"] in calls
    assert ["flatpak", "install", "-y", "flathub", "org.gnome.Extensions"] in calls


# ---------------------------------------------------------------------------
# Ubuntu — GnomeThemeBundle
# ---------------------------------------------------------------------------


def test_gnome_theme_bundle_installs_adw_gtk3_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    GnomeThemeBundle().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "adw-gtk3", "papirus-icon-theme"] in calls


def test_gnome_theme_bundle_verify_uses_dpkg_on_ubuntu() -> None:
    """verify() should call dpkg -s adw-gtk3 (not rpm -q) on Ubuntu."""
    ctx = _ubuntu_ctx(scripts={"dpkg": Result(0)})
    assert GnomeThemeBundle().verify(ctx) is True
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("dpkg" in c[0] and "adw-gtk3" in c for c in calls)


def test_gnome_theme_bundle_verify_false_when_not_installed_on_ubuntu() -> None:
    ctx = _ubuntu_ctx(scripts={"dpkg": Result(1)})
    assert GnomeThemeBundle().verify(ctx) is False


def test_gnome_theme_bundle_installs_fedora_packages_on_fedora() -> None:
    ctx = _ctx()
    GnomeThemeBundle().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "adw-gtk3-theme", "papirus-icon-theme"] in calls


def test_gnome_theme_bundle_verify_uses_rpm_on_fedora() -> None:
    ctx = _ctx(scripts={"rpm": Result(0)})
    assert GnomeThemeBundle().verify(ctx) is True
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("rpm" in c[0] and "adw-gtk3-theme" in c for c in calls)


# ---------------------------------------------------------------------------
# Ubuntu — GnomeAestheticsBundle
# ---------------------------------------------------------------------------


def test_gnome_aesthetics_bundle_installs_gnome_shell_extensions_on_ubuntu() -> None:
    ctx = _ubuntu_ctx()
    GnomeAestheticsBundle().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert (
        ["sudo", "apt-get", "install", "-y", "gnome-shell-extensions", "fonts-noto-core"]
        in calls
    )


def test_gnome_aesthetics_bundle_verify_uses_dpkg_on_ubuntu() -> None:
    ctx = _ubuntu_ctx(scripts={"dpkg": Result(0)})
    assert GnomeAestheticsBundle().verify(ctx) is True
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("dpkg" in c[0] and "gnome-shell-extensions" in c for c in calls)


def test_gnome_aesthetics_bundle_installs_fedora_packages_on_fedora() -> None:
    ctx = _ctx()
    GnomeAestheticsBundle().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    flat = " ".join(" ".join(c) for c in calls)
    assert "gnome-shell-extension-user-theme" in flat
    assert "google-noto-sans-fonts" in flat
