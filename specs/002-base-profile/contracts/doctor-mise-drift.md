# Contract: `doctor` runtime-manager drift warning (engine touch, sanctioned)

A minimal, generic addition to `bin/devboost::cmd_doctor` (no per-module branching),
mirroring Spec 1's `secrets_doctor` delegation.

## `lib/pkg.sh::mise_drift`
- Returns/prints whether BOTH `mise` and a legacy manager are active:
  - `mise` active = `command -v mise` succeeds;
  - legacy active = an **uncommented** nvm/sdkman shell-hook line is present in
    `~/.bashrc` (a line referencing `NVM_DIR`/`nvm.sh` or `SDKMAN_DIR`/`sdkman-init.sh`
    that does not start with optional whitespace then `#`).
  - **Directory presence alone (`~/.nvm`, `~/.sdkman`) is NOT sufficient** — the mise
    migration deliberately leaves those directories intact and only comments out the
    bashrc init hooks (SC-004).  A machine whose hooks have been commented out by the
    migration is NOT in drift, even if the legacy directories still exist.
- Read-only; no writes.

## `cmd_doctor` addition
- Source `lib/pkg.sh`; call `mise_drift`; if drift detected → `log_warn "runtime managers:
  mise and a legacy manager (nvm/sdkman) are both active — migrate or disable the legacy
  one"`. This is a WARNING, never a hard fail (does not set the doctor failure flag).
- All existing doctor checks (python3/jq/OS/modules/age/secrets) unchanged.

## Tests (`tests/doctor-mise.bats`)
- Both active (stub `mise` on PATH + **uncommented** nvm or sdkman init block in scratch
  `~/.bashrc`) → doctor prints the drift warning, still exits 0 (warning ≠ hard fail).
- Post-migration (mise present + legacy dirs exist + bashrc hooks **commented**) → doctor
  emits NO drift warning (SC-004 regression guard).
- Only mise active (no legacy hook in bashrc) → no drift warning.
- Neither / only legacy → no drift warning.
