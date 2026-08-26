# dev-boost — Fedora Hyprland desktop profile (design)

**Date:** 2026-08-26
**Status:** Design — pending user review before writing the implementation plan
**Scope:** One opt-in `hyprland` desktop profile (plus `hyprland-theme` and opt-in
`hyprland-matugen`) for the dev-boost spec-014 typed-Python engine. A curated Hyprland
(Wayland tiling) **side session** that coexists with the existing GNOME desktop; GNOME
remains the default `full` desktop and the always-available fallback.

## 1. Motivation & non-goals

### Why
Omarchy (DHH's Arch + Hyprland distro) is genuinely more attractive and more
keyboard-ergonomic out of the box than vanilla GNOME. The desirable parts —
tiling ergonomics, a single-palette theming system, and sensible curated defaults — are
**aesthetic/ergonomic, not performance** (idle-RAM savings of ~0.5–1.2 GB are a 3–7%
rounding error against this platform's real Docker/Aspire/emulator memory pressure, and
there is no evidence Hyprland is faster under load). Those parts can be delivered on
Fedora without re-platforming dev-boost onto Arch/pacman and without inheriting Arch's
rolling-release risk or Omarchy's `~/.config`-ownership conflict with chezmoi.

This profile brings the Omarchy "feel" to dev-boost's existing Fedora/dnf/chezmoi
foundation as an **opt-in profile**, exactly like the existing `gnome-aesthetics` and
`gnome-theme` opt-in profiles.

### Non-goals (YAGNI / scope guard)
- **No `full-hyprland` aggregate.** `full` stays GNOME. Hyprland is a session you pick at
  the GDM login screen, not the default workstation desktop.
- **No display-manager swap.** GDM (already installed with GNOME) launches both sessions.
- **No GNOME removal or degradation.** GNOME is the guaranteed fallback.
- **No Quickshell / plugin runtime.** Omarchy's Quattro plugin system is QML shell
  chrome; it has no analog or value in a chezmoi/dnf provisioning model.
- **No Arch/pacman/AUR.** Fedora dnf + one named COPR only (see §4).

## 2. Grounding facts (verified 2026-08-26)

- **Fedora 44 does not package Hyprland core.** On a live F44 box with official repos +
  RPM Fusion enabled, only `hyprcursor` (a dependency lib) is available. `hyprland`,
  `hyprlock`, `hypridle`, `hyprpaper`, `hyprpolkitagent`, `xdg-desktop-portal-hyprland`,
  and `swaync` are **absent**. → Hyprland core must come from **COPR `solopasha/hyprland`**
  (the de-facto standard Fedora Hyprland COPR).
- **Peripherals are in official Fedora 44 repos:** `waybar` (0.15), `fuzzel` (1.14),
  `wofi` (1.5), `mako` (1.11), `grim` (1.5), `slurp` (1.5), `matugen` (3.1), `blueman`
  (2.4), `network-manager-applet` (1.36).
- **chezmoi** (`/websites/chezmoi_io`, context7): `.chezmoidata/*.toml` holds static data
  consumed by `.tmpl` templates; `dot_` prefix maps to `~/.<name>`. **`.chezmoidata`
  files cannot themselves be templates** — they must be static and exist before the
  template engine runs. Our palette is static data → compatible.
- **Hyprland** (`/hyprwm/hyprland-wiki`, context7): `source = ~/.config/hypr/*.conf`
  includes are confirmed and parsed linearly; environment variables set via the
  hyprlang INI form `env = KEY,VALUE` (a newer Lua `hl.env("KEY","VALUE")` form also
  exists — this design uses the mainstream INI form the COPR default ships).
- **matugen** (`/iniox/matugen`, context7): `matugen image <wallpaper>` generates a
  Material palette; a `[templates]` section renders `input_path → output_path` with
  `{{colors.<color>.<scheme>.<format>}}` keywords and optional `post_hook`. **Native
  matugen writes directly into its configured output paths** — see §5 for how we contain
  this to preserve chezmoi's sole ownership of `~/.config`.

## 3. Profiles

Added to `profiles.toml`. `full` is unchanged.

```toml
hyprland = ["hyprland-core","hyprland-portal","hyprland-bar","hyprland-launcher",
            "hyprland-notify","hyprland-lock","hyprland-idle","hyprland-wallpaper",
            "hyprland-polkit","hyprland-shot","hyprland-tray","hyprland-session",
            "hyprland-env"]
hyprland-theme    = ["hyprland-theme-bundle"]   # pinned deterministic palette (default)
hyprland-matugen  = ["hyprland-matugen"]         # opt-in wallpaper-driven regeneration
```

- `hyprland` depends on the existing `shell` profile (wezterm, starship, nerd-fonts,
  `wl-clipboard`, dotfiles) being present for a complete experience, but does not
  re-declare those modules; it is intended to be installed alongside `shell`/`cli`.
- `hyprland-theme` is recommended-alongside but kept separate so the compositor can be
  installed without committing to the theming layer.

## 4. Modules

All in a new `engine/src/devboost/modules/hyprland.py` (mirrors `gnome.py`). Each is
`@register`-decorated, subclasses `Module` or `PackageModule`, implements
`verify()`/`install()`, and dispatches on `ctx.os.family`.

| Module | name | Base | Source | Purpose |
|---|---|---|---|---|
| Compositor | `hyprland-core` | `PackageModule` (`copr_repo="solopasha/hyprland"`) | COPR | `hyprland` compositor |
| Portal | `hyprland-portal` | `Module` | COPR | `xdg-desktop-portal-hyprland` (+ `xdg-desktop-portal-gtk`) — screen-share/screenshot backend |
| Bar | `hyprland-bar` | `PackageModule` | official | `waybar` |
| Launcher | `hyprland-launcher` | `PackageModule` | official | `fuzzel` |
| Notify | `hyprland-notify` | `PackageModule` | official | `mako` |
| Lock | `hyprland-lock` | `PackageModule` (COPR) | COPR | `hyprlock` |
| Idle | `hyprland-idle` | `PackageModule` (COPR) | COPR | `hypridle` |
| Wallpaper | `hyprland-wallpaper` | `PackageModule` (COPR) | COPR | `hyprpaper` |
| Polkit | `hyprland-polkit` | `PackageModule` (COPR) | COPR | `hyprpolkitagent` (auth dialogs) |
| Screenshot | `hyprland-shot` | `Module` | official | `grim` + `slurp` |
| Tray | `hyprland-tray` | `Module` | official | `network-manager-applet` + `blueman` |
| Session | `hyprland-session` | `Module` | — | verify GDM present + wayland-session `.desktop` exists |
| Env | `hyprland-env` | `Module` | — | ensure chezmoi-managed `~/.config/hypr/env.conf` applied |
| Theme | `hyprland-theme-bundle` | `Module` | — | pinned palette + templates (no packages) |
| Matugen | `hyprland-matugen` | `Module` | official | `matugen` + `devboost hyprland retheme` path |

### COPR containment
Exactly the `hypr*` core + `xdg-desktop-portal-hyprland` (7 packages) come from
`solopasha/hyprland`. Everything else is official Fedora. This is the profile's **single
external supply-chain dependency**, isolated to the named modules above and enabled via
the existing `copr` primitive (`copr.enable(ctx, "solopasha/hyprland")`), matching how
other COPR-sourced modules already work in the engine. This is a deliberate, documented
tradeoff: GNOME is 100% official-repo; the Hyprland profile is not.

### Representative module shapes

```python
# engine/src/devboost/modules/hyprland.py (excerpt)
from __future__ import annotations
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._pkgmodule import PackageModule


@register
class HyprlandCore(PackageModule):
    name = "hyprland-core"
    category = "hyprland"
    description = "Hyprland Wayland compositor (from solopasha/hyprland COPR on Fedora)."
    gui = True
    profiles = ("hyprland",)
    cmd = "Hyprland"
    fedora_pkg = "hyprland"
    debian_pkg = "hyprland"           # in Debian/Ubuntu repos; no COPR there
    copr_repo = "solopasha/hyprland"  # Fedora-only; ignored on debian family
    self_updating = True


@register
class HyprlandPortal(Module):
    name = "hyprland-portal"
    category = "hyprland"
    description = "xdg-desktop-portal-hyprland — screen-share/screenshot backend."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, "xdg-desktop-portal-hyprland")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "xdg-desktop-portal-hyprland", "xdg-desktop-portal-gtk")


@register
class HyprlandSession(Module):
    name = "hyprland-session"
    category = "hyprland"
    description = "Verify GDM + the Hyprland wayland session so it is selectable at login."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        # session file is shipped by the hyprland package; we only confirm it is present
        # and that GDM (already installed by the gnome path) is the display manager.
        return ctx.ex.exists("/usr/share/wayland-sessions/hyprland.desktop")

    def install(self, ctx: Ctx) -> None:
        # No-op beyond the dependency on hyprland-core; present for an explicit verify
        # gate and a clear failure message if GDM/session file is missing.
        ...
```

`NVIDIA` env values in `hyprland-env` are emitted only when the existing `gpu-detect`
reports an NVIDIA GPU — reusing the same detection the `hardware-nvidia` profile relies
on; no new GPU logic is introduced.

## 5. Theming architecture

Omarchy's best idea — **one palette → many apps** — implemented the chezmoi-native way so
that **chezmoi remains the sole writer of `~/.config`** (the property that avoids
Omarchy's conflict).

### Source layout (in the chezmoi source repo, `dotfiles/`)

```
dotfiles/
├── .chezmoidata/palette.toml            # THE pinned palette — static data (accent, bg,
│                                         #   fg, muted, color0..color15). Not a template.
├── dot_config/hypr/hyprland.conf         # static: keybinds, window rules; `source`s the below
├── dot_config/hypr/colors.conf.tmpl      # ← palette
├── dot_config/hypr/env.conf.tmpl         # Wayland/Electron/NVIDIA env (see §6)
├── dot_config/waybar/config              # static
├── dot_config/waybar/style.css.tmpl      # ← palette
├── dot_config/fuzzel/fuzzel.ini.tmpl     # ← palette
├── dot_config/mako/config.tmpl           # ← palette
├── dot_config/wezterm/colors.lua.tmpl    # existing wezterm config, now palette-driven
└── dot_config/btop/themes/devboost.theme.tmpl  # ← palette
```

Templates reference `{{ .palette.accent }}` etc. Editing `palette.toml` and running
`chezmoi apply` retints the entire desktop in one step. Fully reproducible and
git-diffable (Constitution Principle III).

### Default: `hyprland-theme-bundle` (profile `hyprland-theme`)
Installs no packages. It ensures the palette + templates are present in the chezmoi
source and applied. Deterministic and pinned.

### Opt-in: `hyprland-matugen` (profile `hyprland-matugen`)
Installs `matugen` (official F44) and provides a `devboost hyprland retheme <wallpaper>`
path. **Containment rule (resolves the matugen↔chezmoi ownership conflict):** matugen is
configured with a **single** template whose `output_path` is the **chezmoi source**
`.chezmoidata/palette.toml` (NOT any `~/.config` path). The flow is:

```
wallpaper.jpg
  → matugen image wallpaper.jpg        (Material palette)
  → renders ONE template → <chezmoi-source>/.chezmoidata/palette.toml
  → chezmoi apply                       (re-renders every *.tmpl above)
```

matugen never writes into `~/.config`; it only produces palette *data*. chezmoi remains
the sole renderer/owner of `~/.config`. Off by default — the user chooses pinned
stability or per-wallpaper dynamism.

## 6. Wayland / Electron / NVIDIA environment

`hyprland-env` guarantees a chezmoi-managed `~/.config/hypr/env.conf`, `source`d from
`hyprland.conf`, pre-setting the variables Omarchy sets so Electron/GTK apps (VS Code,
Bruno, dbgate, Bitwarden, Obsidian) render natively on Wayland instead of blurry under
XWayland fractional scaling:

```ini
# ~/.config/hypr/env.conf  (hyprlang INI form)
env = ELECTRON_OZONE_PLATFORM_HINT,auto
env = MOZ_ENABLE_WAYLAND,1
env = XDG_CURRENT_DESKTOP,Hyprland
# --- NVIDIA branch: emitted by the template only when gpu-detect == nvidia ---
env = LIBVA_DRIVER_NAME,nvidia
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = NVD_BACKEND,direct
```

The NVIDIA lines are guarded by a chezmoi template conditional keyed on the existing
GPU-detection output, so an AMD/Intel machine never receives NVIDIA env.

## 7. Keybindings (curated defaults, static in `hyprland.conf`)

Chosen to match existing muscle memory and stay close to Omarchy defaults:

| Bind | Action |
|---|---|
| `Super+Return` | launch wezterm |
| `Super+Space` | fuzzel (app launcher) |
| `Super+Q` | close active window |
| `Super+[1-9]` | switch to workspace N |
| `Super+Shift+[1-9]` | move window to workspace N |
| `Super+F` | toggle fullscreen |
| `Super+V` | toggle floating |
| `Super+H/J/K/L` | focus left/down/up/right |
| `Print` / `Shift+Print` | region / full screenshot via `grim`+`slurp` |
| `Super+Escape` | `hyprlock` |

Documented here so the set is deliberate, not accidental.

## 8. Testing

Consistent with the existing module test pattern (`engine/tests/modules/`), all unit
tests run against a fake `Executor` — no live Hyprland required:

- Each `PackageModule` asserts the correct `pkg.install` package names and, for COPR
  modules, that `copr.enable(ctx, "solopasha/hyprland")` is called on the fedora family
  and **not** on the debian family.
- `hyprland-portal` / `-shot` / `-tray` assert their multi-package installs and
  `verify()` truthiness against faked `pkg.installed` / `which`.
- `hyprland-env` asserts the NVIDIA env branch is present only when GPU-detect is faked to
  `nvidia`, absent otherwise.
- `hyprland-matugen` asserts matugen's configured output path is the chezmoi source
  `.chezmoidata/palette.toml` and never a `~/.config` path (guards the ownership rule).
- `mypy --strict` + ruff clean; these are merge gates per the constitution.

### Manual VM acceptance checklist (goes in the plan as the sign-off gate)
1. Install `hyprland hyprland-theme` on a Fedora 44 VM; reboot.
2. GDM shows both "GNOME" and "Hyprland"; log into Hyprland.
3. wezterm (`Super+Return`) and fuzzel (`Super+Space`) work; keybinds behave.
4. VS Code + Bruno render sharp (no XWayland blur) — confirms `env.conf`.
5. Screen-share a window/screen in Google Meet (Chromium) — confirms the portal.
6. `chezmoi apply` after editing `palette.toml` retints waybar + wezterm + mako.
7. (If `hyprland-matugen` installed) `devboost hyprland retheme <wallpaper>` updates the
   palette and re-themes, with no writes to `~/.config` outside chezmoi.
8. Log out → log into GNOME to confirm the fallback is intact.

## 9. Risks & tradeoffs

- **COPR dependency (`solopasha/hyprland`)** for Hyprland core — single-maintainer supply
  chain, unlike the all-official GNOME path. Accepted and documented; contained to §4
  modules. Mitigation: the profile is opt-in and GNOME remains the default/fallback.
- **Rolling-ish desktop on a stable base** — the COPR tracks Hyprland closely; a Hyprland
  release can shift config semantics. Mitigation: session coexistence means a broken
  Hyprland update never blocks work (log into GNOME); dev-boost pins nothing here beyond
  what the COPR provides.
- **Screen-share / multi-monitor** under Hyprland is less turnkey than GNOME's portal.
  Mitigation: `hyprland-portal` installs the correct backend; acceptance step 5 gates it.
- **Maintenance surface** — 15 new modules + a template set. Mitigation: 9 are trivial
  `PackageModule`s; theming templates are static text; all covered by fake-Executor tests.

## 10. Out of scope / future
- Ubuntu/Debian Hyprland parity (modules dispatch on `ctx.os.family` already, but the
  debian path is untested here and not a goal for this spec).
- A `full-hyprland` aggregate profile (explicitly rejected in §1).
- Wallpaper management daemon choices beyond `hyprpaper`.
