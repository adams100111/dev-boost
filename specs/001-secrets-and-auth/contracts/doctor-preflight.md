# Contract: `doctor` + entrypoint preflight (engine touch)

Two minimal, generic preflight additions. No per-module branching.

## `bin/devboost` — `cmd_doctor`
Add to the existing checks (python3, jq, OS, modules dir):
- `have age || { log_error "age missing"; ok=1; }`
- Source `lib/secrets.sh` and call `secrets_doctor`:
  - `ok`        → `log_ok "secrets: ready"`
  - `missing`   → `log_warn "secrets: no bundle found (set --secrets / $DEVBOOST_SECRETS)"` (warning, not hard-fail: doctor reports; the credentialed modules fail fast when actually run)
  - `cannot-decrypt` → `log_error "secrets: bundle present but cannot decrypt"; ok=1`
  - `incomplete`     → `log_error "secrets: bundle missing required field(s)"; ok=1`

Doctor remains a read-only report; exit non-zero only on hard errors (age missing,
undecryptable/incomplete bundle), consistent with current behavior.

## `install.sh` (entrypoint) preflight
The bootstrap "guarantee python3 + jq + age" step (design §2): extend the existing
preflight so `age` is installed if absent (same per-OS commands as `modules/secrets`),
before any module runs. Keep python3/jq behavior unchanged.

## Test contract (`tests/doctor.bats`)
- age present + decryptable fixture bundle → doctor exits 0, prints "secrets: ready".
- bundle absent → doctor warns "no bundle", does not hard-fail solely for that.
- bundle present + bad key (stub `age` exits non-zero) → doctor exits non-zero,
  "cannot decrypt".
- `age` stub removed from PATH → doctor exits non-zero, "age missing".
