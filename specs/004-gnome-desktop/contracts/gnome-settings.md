# Contract: `gnome-settings` (US1)

Escape-hatch module sourcing `lib/log.sh`+`lib/gnome.sh`. `category="gnome"`, `requires=[]`.

## dconf dump — repo data file `modules/gnome-settings/gnome.dconf` (F1/F2)
A plain version-controlled dconf INI loaded to `/org/gnome/` (NOT a chezmoi `dot_` source).
Reference keys (exact values pinned in impl): `interface/color-scheme='prefer-dark'`,
`interface/accent-color`, `mutter/experimental-features=['scale-monitor-framebuffer']`,
`wm/preferences/button-layout='appmenu:minimize,maximize,close'`, `mutter/center-new-windows=true`,
`peripherals/touchpad/tap-to-click=true`. NO secrets. **No `enabled-extensions`** (owned by `gnome-extensions`).

## `install.sh`
1. `gnome_require` (unsupported if not GNOME).
2. `dconf_load_managed "$DEVBOOST_ROOT/modules/gnome-settings/gnome.dconf"` (single mechanism — load the repo dump).
- `verify`: `[ "$(gsettings get org.gnome.desktop.interface color-scheme)" = "'prefer-dark'" ]`
  (representative key) — idempotent; re-run = no change.

## Tests (`tests/gnome-settings.bats`) — stubbed gsettings/dconf/gnome-shell
- apply → color-scheme/accent/scaling/button-layout/tap-to-click set to reference; verify green.
- re-run → no change (idempotent skip).
- GNOME absent → unsupported failure (not skip).
