"""gnome profile — reference settings (dconf), functional extensions, manager apps."""

from __future__ import annotations

import os

from devboost.core.registry import register
from devboost.exec.primitives import flatpak, pkg
from devboost.exec.resources import resource_path
from devboost.model import Ctx, Module
from devboost.modules.base import Flatpak as FlatpakModule

_DCONF_DUMP = ("data", "gnome", "gnome.dconf")

_FUNCTIONAL_UUIDS = (
    "appindicatorsupport@rgcjonas.gmail.com",
    "clipboard-indicator@tudmotu.com",
    "caffeine@patapon.info",
    "gsconnect@andyholmes.github.io",
    "dash-to-dock@micxgx.gmail.com",
    "emoji-copy@felipeftn",
)


@register
class GnomeSettings(Module):
    name = "gnome-settings"
    category = "gnome"
    description = "Apply the reference GNOME look-and-feel via a dconf dump."
    gui = True
    profiles = ("gnome",)

    def verify(self, ctx: Ctx) -> bool:
        out = ctx.ex.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
        return "prefer-dark" in out.stdout

    def install(self, ctx: Ctx) -> None:
        dump_path = resource_path(*_DCONF_DUMP)
        dump_text = dump_path.read_text(encoding="utf-8")
        if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            ctx.ex.run(["dconf", "load", "/"], stdin=dump_text)
        else:
            # headless firstboot: spawn a temporary dbus session so dconf can write
            ctx.ex.run(["dbus-run-session", "--", "dconf", "load", "/"], stdin=dump_text)


@register
class GnomeExtensions(Module):
    name = "gnome-extensions"
    category = "gnome"
    description = "Install + enable the functional GNOME extension set (session-free via gext)."
    gui = True
    requires = (GnomeSettings,)
    profiles = ("gnome",)

    def verify(self, ctx: Ctx) -> bool:
        enabled = ctx.ex.run(
            ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]
        ).stdout
        return all(uuid in enabled for uuid in _FUNCTIONAL_UUIDS)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("gext"):
            if ctx.os.family == "fedora":
                pkg.install(ctx, "python3-gnome-extensions-cli")
            else:
                # Ubuntu/Debian: no apt package for gext; install via pip3
                if not ctx.ex.which("pip3"):
                    pkg.install(ctx, "python3-pip")
                ctx.ex.run(["pip3", "install", "--user", "gnome-extensions-cli"])
        for uuid in _FUNCTIONAL_UUIDS:
            ctx.ex.run(["gext", "install", uuid])
            ctx.ex.run(["gext", "enable", uuid])


@register
class GnomeManagerApps(Module):
    name = "gnome-manager-apps"
    category = "gnome"
    description = "GNOME Tweaks + Extensions app + Extension Manager (flatpak)."
    gui = True
    requires = (GnomeSettings, FlatpakModule)
    profiles = ("gnome",)

    def verify(self, ctx: Ctx) -> bool:
        flatpaks = ctx.ex.run(["flatpak", "list"]).stdout
        return (
            ctx.ex.which("gnome-tweaks")
            and "com.mattjakeman.ExtensionManager" in flatpaks
            and (ctx.ex.which("gnome-extensions") or "org.gnome.Extensions" in flatpaks)
        )

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            pkg.install(ctx, "gnome-extensions-app", "gnome-tweaks")
        else:
            # Ubuntu/Debian: gnome-tweaks is in apt; gnome-extensions-app is not packaged
            pkg.install(ctx, "gnome-tweaks")
        flatpak.remote_add(ctx, "flathub", "https://flathub.org/repo/flathub.flatpakrepo")
        flatpak.install(ctx, "com.mattjakeman.ExtensionManager")
        flatpak.install(ctx, "org.gnome.Extensions")


@register
class GnomeThemeBundle(Module):
    name = "gnome-theme-bundle"
    category = "gnome"
    description = "Opt-in reproducible GTK theme + icons (adw-gtk3 + papirus)."
    gui = True
    profiles = ("gnome-theme",)

    def _theme_pkg(self, ctx: Ctx) -> str:
        return "adw-gtk3-theme" if ctx.os.family == "fedora" else "adw-gtk3"

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, self._theme_pkg(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            pkg.install(ctx, "adw-gtk3-theme", "papirus-icon-theme")
        else:
            # Ubuntu/Debian: adw-gtk3 (universe) + papirus-icon-theme
            pkg.install(ctx, "adw-gtk3", "papirus-icon-theme")


@register
class GnomeAestheticsBundle(Module):
    name = "gnome-aesthetics-bundle"
    category = "gnome"
    description = "Opt-in aesthetic extras (fonts + theming helpers)."
    gui = True
    profiles = ("gnome-aesthetics",)

    def _usertheme_pkg(self, ctx: Ctx) -> str:
        # Fedora: standalone extension package; Ubuntu: gnome-shell-extensions bundle
        if ctx.os.family == "fedora":
            return "gnome-shell-extension-user-theme"
        return "gnome-shell-extensions"

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, self._usertheme_pkg(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            pkg.install(ctx, "gnome-shell-extension-user-theme", "google-noto-sans-fonts")
        else:
            # Ubuntu/Debian: gnome-shell-extensions (includes user-theme) + fonts-noto-core
            pkg.install(ctx, "gnome-shell-extensions", "fonts-noto-core")
