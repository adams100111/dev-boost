"""macOS desktop apps (spec §2 casks). Every one is free for commercial use (D3-D5).

`profiles.toml` membership for `macos-desktop` and `macos-extras` is filled by the
integration lane, not here (lanes.md §2: `profiles.toml` is an owner-only file, owned by
M5-W0/M5-I, not M5-C) — see lane-C-report.md for the exact lists this file registers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.model import Ctx, Module, TccGrant
from devboost.modules._brew import BrewCask
from devboost.modules._cask import CaskApp
from devboost.modules.macos import Homebrew  # M5-D1 — Homebrew lives in modules.macos
from devboost.modules.shell import Dotfiles

_DESKTOP = ("macos-desktop",)


@register
class Stats(CaskApp):
    name = "stats"
    category = "macos-desktop"
    description = "Stats — menu-bar CPU/RAM/disk/network monitor (MIT)."
    profiles = _DESKTOP
    cask = "stats"
    launch = "Stats"


@register
class Raycast(CaskApp):
    name = "raycast"
    category = "macos-desktop"
    description = "Raycast — launcher and clipboard/window tools (free plan; OK for work)."
    profiles = _DESKTOP
    cask = "raycast"
    launch = "Raycast"
    tcc = (TccGrant("Accessibility", "Raycast"),)


@register
class Aerospace(CaskApp):
    name = "aerospace"
    category = "macos-desktop"
    description = "AeroSpace — i3-like tiling window manager (MIT); config via dotfiles."
    profiles = _DESKTOP
    cask = "nikitabobko/tap/aerospace"
    launch = "AeroSpace"
    after = (Dotfiles,)  # first launch reads ~/.config/aerospace/aerospace.toml
    tcc = (TccGrant("Accessibility", "AeroSpace"),)


@register
class AltTab(CaskApp):
    name = "alt-tab"
    category = "macos-desktop"
    description = "AltTab — Windows-style window switcher with previews (GPL-3.0)."
    profiles = _DESKTOP
    cask = "alt-tab"
    launch = "AltTab"
    tcc = (TccGrant("Accessibility", "AltTab"), TccGrant("ScreenCapture", "AltTab"))


@register
class Thaw(CaskApp):
    name = "thaw"
    category = "macos-desktop"
    description = "Thaw — menu-bar item manager (GPL-3.0; macOS 26+)."
    profiles = _DESKTOP
    cask = "thaw"
    launch = "Thaw"
    min_macos = (26, 0)
    tcc = (TccGrant("Accessibility", "Thaw"), TccGrant("ScreenCapture", "Thaw"))


@register
class MonitorControl(CaskApp):
    name = "monitorcontrol"
    category = "macos-desktop"
    description = "MonitorControl — external-display brightness/volume over DDC (MIT)."
    profiles = _DESKTOP
    cask = "monitorcontrol"
    launch = "MonitorControl"
    tcc = (TccGrant("Accessibility", "MonitorControl"),)


@register
class Keka(CaskApp):
    name = "keka"
    category = "macos-desktop"
    description = "Keka — archiver (7z, zip, rar, ...); free from keka.io."
    profiles = _DESKTOP
    cask = "keka"


#: (cask, app name) — both are Quick Look *app extensions*, registered by one `qlmanage -r`.
_QUICKLOOK = (("qlmarkdown", "QLMarkdown"), ("syntax-highlight", "Syntax Highlight"))


@dataclass(frozen=True)
class _QuickLookInstall:
    """Two casks, each a Quick Look app extension (M5-D6's wrap-BrewCask discipline
    applies to each). `qlmanage -r` restarts the Quick Look server so Finder picks the
    new extensions up; it only runs when this call actually installed one of them, so a
    force `--update` re-run of an already-registered pair does not touch it again."""

    uses_brew: ClassVar[bool] = True

    def _strategies(self) -> tuple[BrewCask, ...]:
        return tuple(BrewCask(cask) for cask, _ in _QUICKLOOK)

    def verify(self, ctx: Ctx) -> bool:
        return all(s.verify(ctx) for s in self._strategies())

    def install(self, ctx: Ctx) -> None:
        installed_now = False
        for (_, app), strat in zip(_QUICKLOOK, self._strategies(), strict=True):
            already = strat.verify(ctx)
            strat.install(ctx)
            if not already:
                ctx.ex.run(["open", "-g", "-a", app])
                installed_now = True
        if installed_now:
            ctx.ex.run(["qlmanage", "-r"])


@register
class Quicklook(Module):
    name = "quicklook"
    category = "macos-desktop"
    description = "Quick Look previews for Markdown and source code (GPL-3.0)."
    profiles = _DESKTOP
    families = ("macos",)
    gui = True
    requires = (Homebrew,)
    per_os = OsMap(macos=_QuickLookInstall())

