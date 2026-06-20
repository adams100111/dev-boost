# Phase 1 Data Model: gnome-desktop

No database. "Data" = module manifests, profile entries, the chezmoi dconf dump, and the
desktop state each module reconciles. Paths overridable in tests.

## Module entities
- Escape-hatch modules (`modules/<name>/{module.toml,install.sh}`) sourcing
  `lib/log.sh`+`lib/pkg.sh`+`lib/gnome.sh`: `gnome-settings`, `gnome-extensions`,
  `gnome-manager-apps`, `gnome-aesthetics` (opt-in), `gnome-theme` (opt-in). All
  `category="gnome"`.

## profiles.toml (EDIT — add 3 entries)
```toml
gnome           = ["gnome-settings","gnome-extensions","gnome-manager-apps"]
gnome-aesthetics = ["gnome-aesthetics"]   # opt-in, NOT in full
gnome-theme     = ["gnome-theme"]         # opt-in, NOT in full
```
`requires`: gnome-extensions/aesthetics `requires=["gnome-settings"]` (the enable-list key
lives in the managed dconf state); gnome-theme `requires=["gnome-settings"]` (applies
theme keys). All require a GNOME desktop (guarded in install.sh, not via profile).

## dconf dump — repo data file `modules/gnome-settings/gnome.dconf` (F1/F2)
A plain version-controlled dconf INI (NOT a chezmoi `dot_` source; the module `dconf load`s
it from the repo). NO secrets. Keys: `[org/gnome/desktop/interface]` color-scheme,
accent-color, font-name (theme); `[org/gnome/mutter]` experimental-features +
center-new-windows; `[org/gnome/desktop/wm/preferences]` button-layout;
`[org/gnome/desktop/peripherals/touchpad]` tap-to-click. **It does NOT contain
`enabled-extensions`** — that key is owned solely by `gnome-extensions` (`ext_enable`).

## State / verify per module
| Module | Verify |
|---|---|
| gnome-settings | a representative key equals reference (e.g. `gsettings get org.gnome.desktop.interface color-scheme` == `'prefer-dark'`) |
| gnome-extensions | each functional UUID dir present AND in `enabled-extensions` |
| gnome-manager-apps | Extensions app + Extension Manager (flatpak) + gnome-tweaks present |
| gnome-aesthetics (opt-in) | each aesthetics UUID present + enabled |
| gnome-theme (opt-in) | User Themes ext present; theme/icon/cursor/font installed + set in dconf |

## Validation rules (from FRs)
| Rule | Source |
|---|---|
| settings declarative + idempotent (dconf load) | FR-001, FR-002 |
| extensions installed by pinned UUID, session-free | FR-003 |
| authorship verified; mismatch → named failure | FR-004, SC-004 |
| enable via enabled-extensions key, no duplicate | FR-005 |
| manager/discovery/tweak apps installed | FR-006 |
| aesthetics + theme OPT-IN (not in full) | FR-007, FR-008, SC-006 |
| reproducible theming, no manual download | FR-008 |
| non-GNOME → unsupported failure (guard) | FR-010, SC-005 |
| no secret in dconf/git | FR-013 |

## Ordering (depsort via requires)
```
gnome-settings → gnome-extensions → (gnome-aesthetics opt-in)
gnome-settings → gnome-theme (opt-in)
all: gnome_require guard (unsupported if not GNOME)
```
