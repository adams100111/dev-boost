# Contract: `lib/gnome.sh` (NEW, sourced)

Source-only helper for GNOME modules. Depends on `lib/log.sh`. All external commands
PATH-stubbable. No side effects on source.

## Functions
- `gnome_require` — die "unsupported: not a GNOME desktop" (non-zero) unless GNOME is
  present (`have gnome-shell` and/or `$XDG_CURRENT_DESKTOP` contains `GNOME`). Called first
  by every gnome module so a non-GNOME host yields a NAMED unsupported failure (FR-010).
- `gnome_shell_version` → prints the major GNOME Shell version (`gnome-shell --version`),
  for gext to fetch the matching extension build.
- `ext_install <UUID>` — `gext install <UUID>` (idempotent: skip if the extension dir
  already exists). Fetches the build for `gnome_shell_version`.
- `ext_verify_author <UUID>` — read the installed `…/<UUID>/metadata.json` and confirm its
  `uuid` field equals `<UUID>` (the UUID embeds the author domain). Non-zero + named on
  mismatch (FR-004).
- `ext_enable <UUID>` — read `gsettings get org.gnome.shell enabled-extensions`, append
  `<UUID>` only if absent (DEDUP), write back with `gsettings set`. Idempotent (FR-005).
- `dconf_load_managed <dump-file>` — `dconf load /org/gnome/ < <dump-file>` (idempotent).

## Guarantees
- `ext_install`+`ext_enable` need NO live GNOME session.
- Failures name the operation. No secret printed. Idempotent throughout.

## Tests (`tests/gnome.bats`) — stubbed gext/gnome-shell/gsettings/dconf
- gnome_require: GNOME-present → ok; absent (`STUB_GNOME_PRESENT=0`) → non-zero "unsupported".
- ext_install skip-when-present; ext_verify_author mismatch → fail; ext_enable adds once,
  no dup on second call; dconf_load_managed records the load.
