# dev-boost — Fedora Hyprland desktop profile (design)

**Date:** 2026-08-26
**Status:** Design — decisions locked (grilled 2026-08-26); pending final user review before the implementation plan
**Scope:** One opt-in `hyprland` desktop profile (plus `hyprland-theme` and opt-in
`hyprland-matugen`) for the dev-boost spec-014 typed-Python engine. A curated Hyprland
(Wayland tiling) **side session** that coexists with the existing GNOME desktop; GNOME
remains the default `full` desktop and the always-available fallback.

## 0. Decisions locked (grilling, 2026-08-26)

| # | Decision | Choice |
|---|---|---|
| Q1 | Palette scope across sessions | **Unified** — one palette themes shared apps (wezterm/starship/btop/tmux) in both GNOME and Hyprland sessions |
| Q2 | GTK / cursor theming under Hyprland | **Minimal** — fixed dark GTK (`adw-gtk3`) + cursor theme; not palette-linked |
| Q3 | HiDPI / monitor scaling | **Auto default** (`monitor = ,preferred,auto,1`) + a per-machine `monitors.conf` override seam (chezmoi-ignored, `source`d) |
| Q4 | Default wallpaper | **Ship one** bundled wallpaper asset in `data/hyprland/` |
| Q5 | COPR module update behavior | **`self_updating = False`** on the `hypr*`-core/COPR modules; official-repo peripherals stay `True` |
| Q6 | Testing | **Both** — scripted config-parse smoke gate + manual VM acceptance checklist |
| Q7 | GDM dependency | **Verify-only** — assume Fedora Workstation base provides GDM; fail loudly if absent |
| Q8 | Screen-share portal routing | **Ship** a chezmoi-managed `~/.config/xdg-desktop-portal/hyprland-portals.conf` |
| Q9 | Palette schema | **base16** (`base00..base0F` + `accent`/`bg`/`fg` aliases) |
| Q10 | Hyprland package source on F44 | **`copr:eddievs/hyprland`** (covers F44 x86_64 + aarch64); ship now, pin + re-verify |

## 1. Motivation & non-goals

### Why
Omarchy (DHH's Arch + Hyprland distro) is genuinely more attractive and more
keyboard-ergonomic out of the box than vanilla GNOME. The desirable parts —
tiling ergonomics, a single-palette theming system, and sensible curated defaults — are
**aesthetic/ergonomic, not performance** (idle-RAM savings of ~0.5–1.2 GB are a 3–7%
rounding error against this platform's real Docker/Aspire/emulator memory pressure, and
there is no evidence Hyprland is faster under load). Those parts can be delivered on
Fedora without re-platforming dev-boost onto Arch/pacman, without inheriting Arch's
rolling-release risk, and without Omarchy's `~/.config`-ownership conflict with chezmoi.

This profile brings the Omarchy "feel" to dev-boost's existing Fedora/dnf/chezmoi
foundation as an **opt-in profile**, exactly like the existing `gnome-aesthetics` and
`gnome-theme` opt-in profiles.

### Non-goals (YAGNI / scope guard)
- **No `full-hyprland` aggregate.** `full` stays GNOME. Hyprland is a session you pick at
  the GDM login screen, not the default workstation desktop.
- **No display-manager swap.** GDM (already in the Fedora Workstation base) launches both.
- **No GNOME removal or degradation.** GNOME is the guaranteed fallback.
- **No Quickshell / plugin runtime.** Omarchy's Quattro plugin system is QML shell
  chrome; it has no analog or value in a chezmoi/dnf provisioning model.
- **No Arch/pacman/AUR.** Fedora dnf + one named COPR only (§4).
- **No palette-driven GTK recoloring** (libadwaita recolor is brittle; see Q2).

## 2. Grounding facts (verified 2026-08-26)

- **Fedora 44 does not package Hyprland core**, and the largest community COPR
  **`solopasha/hyprland` is rawhide-only — it does NOT build for F44** (its only active
  chroot is `fedora-rawhide-x86_64`; `fedora-44-*` results dirs and the `dnf copr enable`
  `.repo` endpoint 404). → Core must come from **`copr:eddievs/hyprland`**, verified to
  build **F44 x86_64 + aarch64** (dev-boost ships both arches). `eli-xciv/hyprland` is an
  equivalent fallback. This is a **smaller-maintainer supply-chain dependency** and is
  the profile's single largest risk (§9).
- **Peripherals are in official Fedora 44 repos:** `waybar` (0.15), `fuzzel` (1.14),
  `mako` (1.11), `grim` (1.5), `slurp` (1.5), `matugen` (3.1), `blueman` (2.4),
  `network-manager-applet` (1.36), `adw-gtk3-theme`, `papirus-icon-theme`.
- **Wayland session file is shipped by the `hyprland` package**
  (`/usr/share/wayland-sessions/hyprland.desktop`), so GDM lists "Hyprland" out of the
  box; `hyprland-session` only verifies it (Q7).
- **GDM is in the base Fedora 44 Workstation install** and reads
  `/usr/share/wayland-sessions/`, so the profile assumes a DM already exists (Q7).
- **chezmoi** (`/websites/chezmoi_io`, context7): `.chezmoidata/*.toml` merges into the
  template data **root** — a flat `palette.toml` with `accent = "…"` is `{{ .accent }}`,
  **not** `{{ .palette.accent }}`. To namespace, the file needs an explicit `[palette]`
  table. `.chezmoidata` files **cannot be templates** (must be static). This design uses a
  `[palette]` table so templates read `{{ .palette.base00 }}` etc.
- **Hyprland config** (`/hyprwm/hyprland-wiki`): `source = ~/.config/hypr/*.conf`
  includes parsed linearly; env via hyprlang INI `env = KEY,VALUE`.
- **matugen** (`/iniox/matugen`): emits Material-3 roles (`primary`, `surface`,
  `on_surface`, …) but templates are pure string substitution with author-controlled
  output keys, so a matugen template can emit our base16 schema
  (`base00 = "{{colors.background.default.hex}}"`, etc.).
- **Portal routing**: the `xdg-desktop-portal-hyprland` package ships `hyprland.portal`
  (`UseIn=…Hyprland…`, `Interfaces=…ScreenCast;Screenshot…`) but **no**
  `hyprland-portals.conf`. With GNOME's portal also installed, backend selection falls
  back to `UseIn` matching (works, but non-deterministic and warns on newer
  xdg-desktop-portal). → we ship an explicit user-level `hyprland-portals.conf` (Q8).

## 3. Profiles

Added to `profiles.toml`. `full` is unchanged. No profile name collides with a module
name (per the profile/module-collision rule): profile `hyprland` vs modules
`hyprland-*`; profile `hyprland-theme` vs module `hyprland-theme-bundle`.

```toml
hyprland = ["hyprland-core","hyprland-portal","hyprland-bar","hyprland-launcher",
            "hyprland-notify","hyprland-lock","hyprland-idle","hyprland-wallpaper",
            "hyprland-polkit","hyprland-shot","hyprland-tray","hyprland-gtk",
            "hyprland-session","hyprland-env"]
hyprland-theme    = ["hyprland-theme-bundle"]   # pinned base16 palette (default)
hyprland-matugen  = ["hyprland-matugen"]         # opt-in wallpaper-driven regeneration
```

`hyprland` is intended to be installed alongside `shell`/`cli` (wezterm, starship,
nerd-fonts, `wl-clipboard`, dotfiles); it does not re-declare those modules.

## 4. Modules

All in a new `engine/src/devboost/modules/hyprland.py` (mirrors `gnome.py`). Each is
`@register`-decorated, subclasses `Module` or `PackageModule`, implements
`verify()`/`install()`, and dispatches on `ctx.os.family`.

| Module | name | Base | Source | Purpose |
|---|---|---|---|---|
| Compositor | `hyprland-core` | `PackageModule` (`copr_repo="eddievs/hyprland"`, `self_updating=False`) | COPR | `hyprland` compositor |
| Portal | `hyprland-portal` | `Module` (`self_updating=False`) | COPR + chezmoi | `xdg-desktop-portal-hyprland` (+`-gtk`) and verify the chezmoi `hyprland-portals.conf` |
| Bar | `hyprland-bar` | `PackageModule` | official | `waybar` |
| Launcher | `hyprland-launcher` | `PackageModule` | official | `fuzzel` |
| Notify | `hyprland-notify` | `PackageModule` | official | `mako` |
| Lock | `hyprland-lock` | `PackageModule` (COPR, `self_updating=False`) | COPR | `hyprlock` |
| Idle | `hyprland-idle` | `PackageModule` (COPR, `self_updating=False`) | COPR | `hypridle` |
| Wallpaper | `hyprland-wallpaper` | `Module` (COPR, `self_updating=False`) | COPR + `data/` | `hyprpaper` + install bundled default wallpaper |
| Polkit | `hyprland-polkit` | `PackageModule` (COPR, `self_updating=False`) | COPR | `hyprpolkitagent` |
| Screenshot | `hyprland-shot` | `Module` | official | `grim` + `slurp` |
| Tray | `hyprland-tray` | `Module` | official | `network-manager-applet` + `blueman` |
| GTK/cursor | `hyprland-gtk` | `Module` | official | `adw-gtk3-theme` + `papirus-icon-theme` + cursor; set via `gsettings` (Q2, minimal) |
| Session | `hyprland-session` | `Module` | — | verify GDM present + wayland-session `.desktop` exists |
| Env | `hyprland-env` | `Module` | — | ensure chezmoi-managed `~/.config/hypr/env.conf` applied |
| Theme | `hyprland-theme-bundle` | `Module` | — | pinned base16 palette + templates (no packages) |
| Matugen | `hyprland-matugen` | `Module` | official | `matugen` + `devboost hyprland retheme` path |

### COPR containment & pinning
Exactly the `hypr*` core + `xdg-desktop-portal-hyprland` come from **`eddievs/hyprland`**,
enabled via the existing `copr` primitive (`copr.enable(ctx, "eddievs/hyprland")`) on the
fedora family only. The COPR is recorded in **`catalog.toml`** (the existing pin
mechanism) with a re-verification note, not hardcoded across modules. All COPR-sourced
modules set **`self_updating = False`** so `devboost install --update` never silently
jumps the compositor (Q5); official-repo peripherals keep the `PackageModule` default
`True`. This is a deliberate, documented tradeoff: GNOME is 100% official-repo; the
Hyprland profile depends on a small third-party maintainer (§9).

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
    description = "Hyprland Wayland compositor (from eddievs/hyprland COPR on Fedora)."
    gui = True
    profiles = ("hyprland",)
    cmd = "Hyprland"
    fedora_pkg = "hyprland"
    debian_pkg = "hyprland"           # in Debian/Ubuntu repos; no COPR there
    copr_repo = "eddievs/hyprland"    # Fedora-only; ignored on debian family
    self_updating = False             # rolling compositor — no silent --update bumps


@register
class HyprlandSession(Module):
    name = "hyprland-session"
    category = "hyprland"
    description = "Verify GDM + the Hyprland wayland session so it is selectable at login."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.exists("/usr/share/wayland-sessions/hyprland.desktop")

    def install(self, ctx: Ctx) -> None:
        # No-op beyond the dependency on hyprland-core; present for an explicit verify
        # gate and a clear failure message if GDM/session file is missing.
        ...
```

`NVIDIA` env values in `hyprland-env` are emitted only when the existing `gpu-detect`
reports an NVIDIA GPU — reusing the detection the `hardware-nvidia` profile relies on.

## 5. Theming architecture (base16, chezmoi-native)

Omarchy's best idea — **one palette → many apps** — implemented so **chezmoi remains the
sole writer of `~/.config`** (the property that avoids Omarchy's conflict). Schema is
**base16** (`base00..base0F`) plus convenience aliases (`accent`, `bg`, `fg`), so any
existing base16 scheme drops in as the pinned default and matugen maps cleanly onto it.

### Source layout (in the chezmoi source repo, `dotfiles/`)

```
dotfiles/
├── .chezmoidata/palette.toml            # static; contains a [palette] table:
│                                         #   [palette]
│                                         #   base00="#…" … base0F="#…"
│                                         #   accent="#…"  bg="#…"  fg="#…"
├── dot_config/hypr/hyprland.conf         # static: keybinds, window rules, exec-once
│                                         #   autostart, monitor default; `source`s below
├── dot_config/hypr/colors.conf.tmpl      # ← {{ .palette.* }}
├── dot_config/hypr/env.conf.tmpl         # Wayland/Electron/NVIDIA env (§6)
├── dot_config/hypr/hyprlock.conf.tmpl    # ← palette (lock screen)
├── dot_config/hypr/hypridle.conf         # static: idle → lock/dpms timings
├── dot_config/hypr/monitors.conf         # per-machine override seam; chezmoi-ignored*
├── dot_config/waybar/config              # static
├── dot_config/waybar/style.css.tmpl      # ← palette
├── dot_config/fuzzel/fuzzel.ini.tmpl     # ← palette
├── dot_config/mako/config.tmpl           # ← palette
├── dot_config/wezterm/colors.lua.tmpl    # existing wezterm config, now palette-driven
├── dot_config/btop/themes/devboost.theme.tmpl   # ← palette
└── dot_config/xdg-desktop-portal/hyprland-portals.conf  # static (Q8, §2)
```

\* `monitors.conf` is listed in the chezmoi source but excluded from management on apply
(via `.chezmoiignore` or a `private_`/local convention) so a machine's display scaling
never gets clobbered; `hyprland.conf` `source`s it if present.

`hyprland.conf` includes an `exec-once` autostart block for the full session:
`waybar`, `mako`, `hyprpaper`, `hypridle`, `hyprpolkitagent`, `nm-applet`, `blueman-applet`.

### Unified palette (Q1)
Shared apps (`wezterm`, `btop`, `starship`, `tmux`) read the same palette, so a palette
change retints them in **both** the GNOME and Hyprland sessions — one consistent look,
no session-conditional branching.

### Default: `hyprland-theme-bundle` (profile `hyprland-theme`)
Installs no packages; ensures the pinned base16 palette + templates are present in the
chezmoi source and applied. Deterministic, pinned, git-diffable (Constitution Principle III).

### Opt-in: `hyprland-matugen` (profile `hyprland-matugen`)
Installs `matugen` (official F44) and provides `devboost hyprland retheme <wallpaper>`.
**Containment rule (preserves chezmoi ownership):** matugen is configured with a **single**
template whose `output_path` is the **chezmoi source** `.chezmoidata/palette.toml` (a
`[palette]` table mapping Material-3 roles → base16), NOT any `~/.config` path. Flow:

```
wallpaper.jpg → matugen image … → renders ONE template → <chezmoi-source>/.chezmoidata/palette.toml
             → chezmoi apply → re-renders every *.tmpl above
```

matugen never writes into `~/.config`; it produces palette *data* only. Off by default.

## 6. Wayland / Electron / NVIDIA environment

`hyprland-env` guarantees a chezmoi-managed `~/.config/hypr/env.conf`, `source`d from
`hyprland.conf`, so Electron/GTK apps (VS Code, Bruno, dbgate, Bitwarden, Obsidian) render
natively on Wayland instead of blurry under XWayland fractional scaling:

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

The NVIDIA lines are guarded by a chezmoi template conditional keyed on GPU-detection
output, so AMD/Intel machines never receive NVIDIA env.

## 7. Keybindings (curated defaults, static in `hyprland.conf`)

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

## 8. Testing (Q6 — both)

Unit tests (fake `Executor`, no live Hyprland), consistent with `engine/tests/modules/`:
- COPR modules assert `copr.enable(ctx, "eddievs/hyprland")` on fedora family and **not**
  on debian; and assert `self_updating is False` on the `hypr*`-core/COPR modules.
- multi-package modules (`hyprland-portal`/`-shot`/`-tray`/`-gtk`) assert package sets and
  `verify()` truthiness against faked `pkg.installed`/`which`.
- `hyprland-env` asserts the NVIDIA env branch present only when GPU-detect is `nvidia`.
- `hyprland-matugen` asserts matugen's configured output path is the chezmoi source
  `.chezmoidata/palette.toml` and never a `~/.config` path (guards the ownership rule).
- `hyprland-portal` asserts the chezmoi `hyprland-portals.conf` is present.
- `mypy --strict` + ruff clean (merge gates).

**Scripted smoke gate (new):** after `chezmoi apply` renders the templates, run a
Hyprland **config-parse check** (`hyprland --config <rendered hyprland.conf> --verify`-style
dry parse, no session) so a template typo fails loudly in CI/VM. This catches the most
likely regression — a broken `.tmpl`.

### Manual VM acceptance checklist (sign-off gate)
1. Install `hyprland hyprland-theme` on a Fedora 44 VM; reboot.
2. GDM shows "GNOME" and "Hyprland"; log into Hyprland.
3. wezterm (`Super+Return`), fuzzel (`Super+Space`), keybinds work; autostart (waybar,
   mako, wallpaper, polkit, tray) all come up.
4. VS Code + Bruno render sharp (no XWayland blur) — confirms `env.conf`.
5. Screen-share a window/screen in Google Meet (Chromium) — confirms portal + `portals.conf`.
6. `chezmoi apply` after editing `palette.toml` retints waybar + wezterm + mako (and,
   per Q1, wezterm/btop under GNOME too).
7. (If `hyprland-matugen`) `devboost hyprland retheme <wallpaper>` updates the palette and
   re-themes, with no writes to `~/.config` outside chezmoi.
8. Log out → into GNOME to confirm the fallback is intact.

## 9. Risks & tradeoffs

- **Third-party COPR (`eddievs/hyprland`)** for Hyprland core — a *small-maintainer*
  supply chain, and the larger `solopasha` COPR does not even cover F44. This is the
  profile's biggest risk and a real dent in the "Fedora-is-more-stable-than-Omarchy"
  thesis. **Mitigations:** opt-in profile; GNOME is the default/fallback; COPR pinned in
  `catalog.toml` with a re-verify note; `self_updating=False` so no silent bumps;
  `eli-xciv/hyprland` documented as a drop-in fallback. Revisit if Hyprland lands in
  official Fedora repos or a Fedora SIG COPR appears.
- **Rolling-ish desktop on a stable base** — a Hyprland release can shift config
  semantics. Mitigation: session coexistence means a broken update never blocks work
  (log into GNOME); config-parse smoke gate catches template breakage early.
- **Screen-share / multi-monitor** less turnkey than GNOME. Mitigation: `hyprland-portal`
  + shipped `hyprland-portals.conf`; acceptance step 5 gates it.
- **Maintenance surface** — 16 modules + a template set. Mitigation: most are trivial
  `PackageModule`s; theming templates are static text; all covered by fake-Executor tests.

## 10. Out of scope / future
- Ubuntu/Debian Hyprland parity (modules dispatch on `ctx.os.family`, but the debian path
  is untested here and not a goal).
- A `full-hyprland` aggregate profile (explicitly rejected in §1).
- Palette-driven GTK/libadwaita recoloring (rejected in Q2 as brittle).
- Wallpaper daemons beyond `hyprpaper`.
