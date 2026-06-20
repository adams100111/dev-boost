# Contract: `gnome-manager-apps` + opt-in `gnome-aesthetics` + `gnome-theme` (US3)

All `category="gnome"`, source `lib/log.sh`+`lib/pkg.sh`+`lib/gnome.sh`, `gnome_require` first.

## gnome-manager-apps (default `gnome`)
- Install: official Extensions app (`gnome-extensions-app` via dnf, OR flatpak
  `org.gnome.Extensions`), Extension Manager (flatpak `com.mattjakeman.ExtensionManager`),
  `gnome-tweaks` (dnf). All add-if-absent/idempotent.
- `verify`: `command -v gnome-tweaks` AND the Extension Manager flatpak present
  (`flatpak list | grep -q com.mattjakeman.ExtensionManager`) AND the Extensions app present.
- `requires=["gnome-settings"]`.

## gnome-aesthetics-bundle (OPT-IN — profile `gnome-aesthetics`, NOT in full)
- `requires=["gnome-settings"]`. Install+enable (via `lib/gnome.sh`, session-free) the
  aesthetics set: `blur-my-shell@aunetx`, `just-perfection-desktop@just-perfection`,
  `vertical-workspaces@G-dH.github.com`, `monitor@astraext.github.io`,
  `CoverflowAltTab@palatis.blogspot.com`. Same author-verify + enable-dedup.
- `verify`: each aesthetics UUID present + enabled.

## gnome-theme-bundle (OPT-IN — profile `gnome-theme`, NOT in full)
- `requires=["gnome-settings"]`. Install: User Themes ext
  (`user-theme@gnome-shell-extensions.gcampax.github.com`, via gext + enable); a pinned
  vinceliuice theme (`git clone` at a TAG → `./install.sh -l -c dark`); `papirus-icon-theme`
  (dnf); Bibata cursor (dnf/COPR); `rsms-inter-fonts` (dnf) + `fc-cache`. Apply via dconf
  keys (gtk-theme/icon-theme/cursor-theme/font-name). NO manual gnome-look.org download.
- `verify`: User Themes enabled AND the theme dir present AND the icon/cursor/font installed
  AND the dconf gtk-theme key set.

## Tests (`tests/gnome-manager.bats`, `tests/gnome-theme.bats`) — stubbed dnf/flatpak/gext/git/gsettings/fc-list
- manager: each app installed once (add-if-absent); verify maps to presence; idempotent.
- aesthetics (module `gnome-aesthetics-bundle`): each UUID installed+enabled (opt-in), idempotent.
- theme (module `gnome-theme-bundle`): User Themes enabled; theme git-clone at the pinned tag + install.sh; papirus/bibata/inter
  installed; dconf theme keys set; reproducible (no gnome-look.org); idempotent; opt-in (absent from `gnome`).
