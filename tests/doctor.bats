load test_helper
load fixtures/secrets/stubs

# T015 — doctor preflight tests per contracts/doctor-preflight.md
#
# All tests run bin/devboost doctor in a subshell with appropriate
# stubs/fixtures from tests/fixtures/secrets/stubs.bash.
#
# bats merges stderr into $output when using `run`.

setup() {
  stubs_setup
  # Point doctor at a real modules dir so the modules-dir check passes.
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  # Use a known OS release so os_detect passes.
  export OS_RELEASE_FILE="${DEVBOOST_ROOT}/tests/fixtures/os-release/fedora"
}

teardown() {
  stubs_teardown
}

# Helper: run devboost doctor with current env (stubs on PATH, bundle wired).
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
# T015-a: age present + decryptable fixture bundle → exit 0, "secrets: ready"
# ---------------------------------------------------------------------------

@test "doctor: age present + valid bundle → exits 0 and prints 'secrets: ready'" {
  # stubs_setup already installed a stub age and wired DEVBOOST_SECRETS to fixture bundle.
  _run_doctor
  [ "$status" -eq 0 ]
  [[ "$output" == *"secrets: ready"* ]]
}

# ---------------------------------------------------------------------------
# T015-b: bundle absent → warns "no bundle", does NOT hard-fail solely for that
# ---------------------------------------------------------------------------

@test "doctor: bundle absent → warns 'no bundle', does not hard-fail" {
  # Remove the bundle path so secrets_doctor returns 'missing'.
  run bash -c "
    export PATH='${PATH}'
    export HOME='${HOME}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_RELEASE_FILE='${OS_RELEASE_FILE}'
    export DEVBOOST_SECRETS='/nonexistent/secrets.age'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='/nonexistent'
    '${DEVBOOST_ROOT}/bin/devboost' doctor
  " 2>&1
  # Must NOT hard-fail solely because bundle is absent.
  [ "$status" -eq 0 ]
  [[ "$output" == *"no bundle"* ]]
}

# ---------------------------------------------------------------------------
# T015-c: bundle present + bad key (age stub exits 1) → exit non-zero, "cannot decrypt"
# ---------------------------------------------------------------------------

@test "doctor: bad key (age fails) → exits non-zero, prints 'cannot decrypt'" {
  run bash -c "
    export PATH='${PATH}'
    export HOME='${HOME}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_RELEASE_FILE='${OS_RELEASE_FILE}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_AGE_FAIL=1
    '${DEVBOOST_ROOT}/bin/devboost' doctor
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"cannot decrypt"* ]]
}

# ---------------------------------------------------------------------------
# T015-d: age absent from PATH → exit non-zero, "age missing"
# ---------------------------------------------------------------------------

@test "doctor: age absent from PATH → exits non-zero, prints 'age missing'" {
  # Override PATH to exclude the stub age (use a temp dir with no age).
  local empty_bin
  empty_bin="$(mktemp -d)"
  run bash -c "
    export PATH='${empty_bin}:/usr/local/bin:/usr/bin:/bin'
    export HOME='${HOME}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_RELEASE_FILE='${OS_RELEASE_FILE}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    '${DEVBOOST_ROOT}/bin/devboost' doctor
  " 2>&1
  rm -rf "${empty_bin}"
  [ "$status" -ne 0 ]
  [[ "$output" == *"age missing"* ]]
}
