load test_helper
load fixtures/base/stubs
load fixtures/secrets/stubs

# T018 — doctor runtime-manager drift warning (FR-008)
# per contracts/doctor-mise-drift.md
#
# bats merges stderr into $output when using `run`.

setup() {
  # base_setup installs mise stub + scratch HOME (with ~/.nvm support via STUB_NVM_VERSION).
  # stubs_setup installs age stub + wires DEVBOOST_SECRETS for the existing doctor checks.
  base_setup
  # stubs_setup creates its own scratch HOME; we need ONE consistent HOME.
  # Call stubs_setup to install the age stub into our PATH, but keep HOME from base_setup.
  local saved_home="${HOME}"
  stubs_setup
  # Restore HOME to the one from base_setup (base_setup set it first and is authoritative
  # for the nvm/sdkman directory structure).
  export HOME="${saved_home}"

  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_RELEASE_FILE="${DEVBOOST_ROOT}/tests/fixtures/os-release/fedora"
}

teardown() {
  base_teardown
  stubs_teardown
}

# Helper: run devboost doctor with the full env forwarded.
_run_doctor() {
  run bash -c "
    export PATH='${PATH}'
    export HOME='${HOME}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_RELEASE_FILE='${OS_RELEASE_FILE}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    '${DEVBOOST_ROOT}/bin/devboost' doctor
  " 2>&1
}

# ---------------------------------------------------------------------------
# T018-a: both mise and legacy active → drift warning printed; doctor not hard-failed
# ---------------------------------------------------------------------------

@test "doctor: mise + nvm both active → prints drift warning" {
  # mise stub is already on PATH (installed by base_setup).
  # Create ~/.nvm directory so mise_drift detects legacy.
  mkdir -p "${HOME}/.nvm"

  _run_doctor
  [[ "$output" == *"runtime managers: mise and a legacy manager (nvm/sdkman) are both active"* ]]
}

@test "doctor: mise + nvm both active → drift warning is a warning not a hard fail" {
  # A passing doctor (age present, secrets wired, OS known, modules dir present)
  # with a drift warning must still exit 0.
  mkdir -p "${HOME}/.nvm"

  _run_doctor
  [ "$status" -eq 0 ]
  [[ "$output" == *"runtime managers: mise and a legacy manager (nvm/sdkman) are both active"* ]]
}

@test "doctor: mise + sdkman both active → prints drift warning" {
  mkdir -p "${HOME}/.sdkman"

  _run_doctor
  [[ "$output" == *"runtime managers: mise and a legacy manager (nvm/sdkman) are both active"* ]]
}

# ---------------------------------------------------------------------------
# T018-b: only mise active (no legacy dirs) → no drift warning
# ---------------------------------------------------------------------------

@test "doctor: only mise active (no legacy dirs) → no drift warning" {
  # mise stub is on PATH; no ~/.nvm or ~/.sdkman.

  _run_doctor
  [[ "$output" != *"runtime managers:"* ]]
}

# ---------------------------------------------------------------------------
# T018-c: neither active (no mise, no legacy) → no drift warning
# ---------------------------------------------------------------------------

@test "doctor: neither mise nor legacy active → no drift warning" {
  base_remove_mise

  _run_doctor
  [[ "$output" != *"runtime managers:"* ]]
}

# ---------------------------------------------------------------------------
# T018-d: only legacy active (no mise) → no drift warning
# ---------------------------------------------------------------------------

@test "doctor: only legacy active (no mise) → no drift warning" {
  base_remove_mise
  mkdir -p "${HOME}/.nvm"

  _run_doctor
  [[ "$output" != *"runtime managers:"* ]]
}
