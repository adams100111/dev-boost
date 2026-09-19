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
from devboost.modules._credentials import is_interactive
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
    force `--update` re-run of an already-registered pair does not touch it again.

    Neither `open` nor `qlmanage -r` pops a TCC dialog these modules would need a grant
    for (`quicklook` declares no `tcc`), but `open` still visibly launches an app and
    `qlmanage -r` restarts a system service — both gated behind
    `_credentials.is_interactive()` (global constraint: nothing pops on an unwatched
    desktop). Unattended, the casks still install; the extensions register themselves
    the next time the user actually opens Finder or the apps by hand — no NeedsUser,
    since there is nothing only a human can unblock here.
    """

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
                installed_now = True
                if is_interactive():
                    ctx.ex.run(["open", "-g", "-a", app])
        if installed_now and is_interactive():
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


# --- macos-extras (opt-in) ----------------------------------------------------------------
# Licences checked 2026-09-19 (D3-D5): all free for work use.

_EXTRAS = ("macos-extras",)


@register
class Maccy(CaskApp):
    name = "maccy"
    category = "macos-extras"
    description = "Maccy — clipboard history (MIT)."
    profiles = _EXTRAS
    cask = "maccy"
    launch = "Maccy"
    tcc = (TccGrant("Accessibility", "Maccy"),)


@register
class OllamaApp(CaskApp):
    name = "ollama-app"
    category = "macos-extras"
    description = "Ollama — run local LLMs (MIT)."
    profiles = _EXTRAS
    cask = "ollama-app"


@register
class LmStudio(CaskApp):
    name = "lm-studio"
    category = "macos-extras"
    description = "LM Studio — local LLM app (free for work use since 2025-07)."
    profiles = _EXTRAS
    cask = "lm-studio"


@register
class Pearcleaner(CaskApp):
    name = "pearcleaner"
    category = "macos-extras"
    description = "Pearcleaner — app uninstaller (Apache-2.0 + Commons Clause)."
    profiles = _EXTRAS
    cask = "pearcleaner"


@register
class Keycastr(CaskApp):
    name = "keycastr"
    category = "macos-extras"
    description = "KeyCastr — show keystrokes on screen for demos (BSD-3-Clause)."
    profiles = _EXTRAS
    cask = "keycastr"
    tcc = (TccGrant("ListenEvent", "KeyCastr"), TccGrant("Accessibility", "KeyCastr"))


@register
class Linearmouse(CaskApp):
    name = "linearmouse"
    category = "macos-extras"
    description = "LinearMouse — per-device mouse/trackpad tuning (MIT)."
    profiles = _EXTRAS
    cask = "linearmouse"
    launch = "LinearMouse"
    tcc = (TccGrant("Accessibility", "LinearMouse"),)


@register
class AndroidStudio(CaskApp):
    name = "android-studio"
    category = "macos-extras"
    description = "Android Studio (Apache-2.0 + Google SDK terms)."
    profiles = _EXTRAS
    cask = "android-studio"


@register
class ExpoOrbit(CaskApp):
    name = "expo-orbit"
    category = "macos-extras"
    description = "Expo Orbit — launch builds on simulators/emulators from the menu bar (MIT)."
    profiles = _EXTRAS
    cask = "expo-orbit"


@register
class Herd(CaskApp):
    name = "herd"
    category = "macos-extras"
    description = "Laravel Herd — native PHP/Laravel environment (free tier; Pro optional)."
    profiles = _EXTRAS
    cask = "herd"
