# Contract: `doctor` runtime-manager drift warning (engine touch, sanctioned)

A minimal, generic addition to `bin/devboost::cmd_doctor` (no per-module branching),
mirroring Spec 1's `secrets_doctor` delegation.

## `lib/pkg.sh::mise_drift`
- Returns/prints whether BOTH `mise` and a legacy manager are active:
  - `mise` active = `command -v mise` succeeds;
  - legacy active = an uncommented nvm/sdkman init line present in `~/.bashrc`, OR
    `~/.nvm`/`~/.sdkman` present AND its shell hook still sourced.
- Read-only; no writes.

## `cmd_doctor` addition
- Source `lib/pkg.sh`; call `mise_drift`; if drift detected → `log_warn "runtime managers:
  mise and a legacy manager (nvm/sdkman) are both active — migrate or disable the legacy
  one"`. This is a WARNING, never a hard fail (does not set the doctor failure flag).
- All existing doctor checks (python3/jq/OS/modules/age/secrets) unchanged.

## Tests (`tests/doctor-mise.bats`)
- Both active (stub `mise` on PATH + fake uncommented nvm block in scratch `~/.bashrc`) →
  doctor prints the drift warning, still exits per other checks (warning ≠ hard fail).
- Only mise active (no legacy) → no drift warning.
- Neither / only legacy → no drift warning.
