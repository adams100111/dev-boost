"""gnome profile — reference settings (dconf), functional extensions, manager apps."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import dconf, flatpak, pkg
from devboost.exec.resources import resource_path
from devboost.model import Ctx, Module

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
        dconf.load(ctx, resource_path(*_DCONF_DUMP))


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
            pkg.install(ctx, "python3-gnome-extensions-cli")
        for uuid in _FUNCTIONAL_UUIDS:
            ctx.ex.run(["gext", "install", uuid])
            ctx.ex.run(["gext", "enable", uuid])


@register
class GnomeManagerApps(Module):
    name = "gnome-manager-apps"
    category = "gnome"
    description = "GNOME Tweaks + Extensions app + Extension Manager (flatpak)."
    gui = True
    requires = (GnomeSettings,)
    profiles = ("gnome",)

    def verify(self, ctx: Ctx) -> bool:
        flatpaks = ctx.ex.run(["flatpak", "list"]).stdout
        return (
            ctx.ex.which("gnome-tweaks")
            and "com.mattjakeman.ExtensionManager" in flatpaks
            and (ctx.ex.which("gnome-extensions") or "org.gnome.Extensions" in flatpaks)
        )

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "gnome-extensions-app", "gnome-tweaks")
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

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", "adw-gtk3-theme"]).ok

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "adw-gtk3-theme", "papirus-icon-theme")


@register
class GnomeAestheticsBundle(Module):
    name = "gnome-aesthetics-bundle"
    category = "gnome"
    description = "Opt-in aesthetic extras (fonts + theming helpers)."
    gui = True
    profiles = ("gnome-aesthetics",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", "gnome-shell-extension-user-theme"]).ok

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "gnome-shell-extension-user-theme", "google-noto-sans-fonts")
