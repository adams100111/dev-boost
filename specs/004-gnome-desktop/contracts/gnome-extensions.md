# Contract: `gnome-extensions` (US2)

Escape-hatch module sourcing `lib/log.sh`+`lib/gnome.sh`. `category="gnome"`,
`requires=["gnome-settings"]`.

## Functional set (pinned UUIDs — default `gnome`)
`appindicatorsupport@rgcjonas.gmail.com`, `clipboard-indicator@tudmotu.com`,
`caffeine@patapon.info`, `gsconnect@andyholmes.github.io`, `dash-to-dock@micxgx.gmail.com`,
`emoji-copy@felipeftn`.

## `install.sh`
1. `gnome_require`.
2. Ensure `gext` available (`ensure_pkg`/pipx).
3. For each pinned UUID: `ext_install` → `ext_verify_author` (named failure on mismatch) →
   `ext_enable` (dedup into enabled-extensions).
- `verify`: every functional UUID dir exists AND appears in
  `gsettings get org.gnome.shell enabled-extensions`.

## Acceptance (maps to spec)
- US2-S1: installed by UUID for detected shell version, added to enable list, no session.
- US2-S2: author/UUID mismatch → named failure (not installed).
- US2-S3: re-run → no re-install, no duplicate enable entry.

## Tests (`tests/gnome-extensions.bats`) — stubbed gext/gnome-shell/gsettings
- each UUID: gext install attempted for the detected version; author verified; added once to
  the enable list; re-run idempotent (no dup — assert count==1 per UUID).
- a fixture extension whose metadata.json UUID mismatches the pinned UUID → named failure.
- GNOME absent → unsupported failure.
