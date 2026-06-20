# Phase 0 Research: gnome-desktop

Spec clarifications settled in specify. Plan-level decisions below.

## D1. Session-free extension install + enable
**Decision**: (1) INSTALL via `gext install <UUID>` (gnome-extensions-cli) which downloads
the matching version for the detected GNOME Shell from extensions.gnome.org into
`~/.local/share/gnome-shell/extensions/<UUID>/` — no session needed. (2) VERIFY authorship:
after install, read the extension's `metadata.json` and confirm the UUID matches the pinned
value (the UUID embeds the author domain, e.g. `…@tudmotu.com`); refuse on mismatch. (3)
ENABLE by reading the current `org.gnome.shell enabled-extensions` list (`gsettings get`),
appending the UUID if absent (dedup), and writing it back (`gsettings set`) — the next
session honors it. No `gnome-extensions enable` (needs live shell).
**Rationale**: matches the spec clarification; fully unattended; idempotent (gext skips
present, enable dedups).
**gext availability**: install via `pipx install gnome-extensions-cli` or dnf/pip; the
`gnome-extensions` CLI (part of gnome-shell) is the fallback for list/info.

## D2. GNOME-present guard (unsupported, not skipped)
**Decision**: `lib/gnome.sh::gnome_require` checks GNOME is the desktop —
`command -v gnome-shell` present (and/or `$XDG_CURRENT_DESKTOP` contains GNOME). If absent,
`die "unsupported: not a GNOME desktop"` (non-zero), which the engine reports as a module
failure (never a silent skip, FR-010/SC-005). Each gnome module's install.sh calls
`gnome_require` first. (GNOME-vs-not is not an OS key, so this is a module guard, not engine
branching — §I preserved.)

## D3. Settings via managed dconf dump
**Decision (F1/F2 resolved)**: ship a **plain repo data file** `modules/gnome-settings/gnome.dconf`
(version-controlled dconf INI; NOT a chezmoi `dot_` source — it is data the module LOADS, not a
file deployed to `~/.config`) containing ONLY look-and-feel keys:
`/org/gnome/desktop/interface/color-scheme='prefer-dark'`,
accent-color, `/org/gnome/mutter/experimental-features=['scale-monitor-framebuffer']`,
`/org/gnome/desktop/wm/preferences/button-layout`, center-new-windows,
`/org/gnome/desktop/peripherals/touchpad/tap-to-click=true`. It does **NOT** contain
`enabled-extensions` — that key is owned SOLELY by `gnome-extensions` (`ext_enable`), giving one
source of truth for the enable list (F2). `gnome-settings/install.sh` runs
`dconf load /org/gnome/ < "$DEVBOOST_ROOT/modules/gnome-settings/gnome.dconf"`. Idempotent (load sets exact values; re-run = no change).
Verify: a representative key equals the reference value (e.g. `gsettings get … color-scheme`).
**Rationale**: declarative + reproducible (design §10c); dconf load is the documented path.
**Gotcha encoded**: dconf keys are GNOME-version-fragile — the module targets the detected
version and fails clearly if a schema key is absent rather than corrupting state.

## D4. Manager apps + theme components (per-OS data)
**Decision**: `gnome-manager-apps`: `org.gnome.Extensions` (dnf `gnome-extensions-app` OR
flatpak `org.gnome.Extensions`), Extension Manager (flatpak `com.mattjakeman.ExtensionManager`),
`gnome-tweaks` (dnf). `gnome-theme` (opt-in): User Themes extension
(`user-theme@gnome-shell-extensions.gcampax.github.com`, via gext) + a pinned vinceliuice
theme (`git clone` at a tag → `./install.sh -l -c dark`) + `papirus-icon-theme` (dnf) +
Bibata cursor (dnf/COPR) + Inter (`rsms-inter-fonts` dnf); applied via the managed dconf
keys (gtk-theme/icon-theme/cursor-theme/font-name). NO manual gnome-look.org (design §10c).

## D5. Curated extension sets (pinned UUIDs)
**Decision** (functional, default `gnome`): `appindicatorsupport@rgcjonas.gmail.com`,
`clipboard-indicator@tudmotu.com`, `caffeine@patapon.info`, `gsconnect@andyholmes.github.io`,
`dash-to-dock@micxgx.gmail.com`, `emoji-copy@felipeftn` (verify author at install).
(aesthetics, opt-in `gnome-aesthetics`): `blur-my-shell@aunetx`,
`just-perfection-desktop@just-perfection`, `vertical-workspaces@G-dH.github.com`,
`monitor@astraext.github.io` (or `Vitals@CoreCoding.com`), `CoverflowAltTab@palatis.blogspot.com`.
Each pinned; authorship verified; installed+enabled via D1.

## D6. Testing (no desktop/installs)
**Decision**: extend `tests/fixtures/base/stubs.bash` with stubs for `gext` (records
install by UUID; writes a fake `~/.local/share/gnome-shell/extensions/<UUID>/metadata.json`
with the UUID so author-verify can run), `gnome-extensions`, `dconf` (load records the dump;
a scratch dconf state), `gsettings` (get/set an in-memory enabled-extensions list + keys),
`gnome-shell` (`--version` via knob), plus a `STUB_GNOME_PRESENT` knob. Tests assert: settings
keys applied + idempotent; each functional UUID installed + author-verified + added once to
the enable list (no dup on re-run); a mismatched-author fixture → named failure; unsupported
(GNOME absent) → failure; opt-in bundles provision reproducibly. No real desktop.
**Rationale**: hermetic, §V real-behavior; mirrors Specs 1–3.

## Outcome
No unresolved NEEDS CLARIFICATION. Ready for Phase 1.
