load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Spec 13 — security-cli: pass + pass-store (GPG + store provisioning). Stubbed gpg/pass/git.

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  base_install_security_stubs
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export PASSWORD_STORE_DIR="${BATS_TEST_TMPDIR}/password-store"
  export STUB_GPG_LOG="${BATS_TEST_TMPDIR}/gpg.log"; : > "${STUB_GPG_LOG}"
  export STUB_PASS_LOG="${BATS_TEST_TMPDIR}/pass.log"; : > "${STUB_PASS_LOG}"
}
teardown() { base_teardown; }

_run_passstore() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export PASSWORD_STORE_DIR='${PASSWORD_STORE_DIR}'
    export STUB_GPG_LOG='${STUB_GPG_LOG}'
    export STUB_PASS_LOG='${STUB_PASS_LOG}'
    export STUB_GPG_KEYS='${STUB_GPG_KEYS:-}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export DEVBOOST_PASS_REPO='${DEVBOOST_PASS_REPO:-}'
    bash '${DEVBOOST_ROOT}/modules/pass-store/install.sh'
  " 2>&1
}
_run_verify() {
  bash -c "export PASSWORD_STORE_DIR='${PASSWORD_STORE_DIR}'; export DEVBOOST_ROOT='${DEVBOOST_ROOT}'; bash '${DEVBOOST_ROOT}/modules/pass-store/verify.sh'" 2>&1
}

@test "pass: installs the pass CLI and verifies" {
  # pass stub is on PATH (verify would skip), so --force exercises the install path;
  # post-install re-verify is green because the stub provides `pass`.
  DEVBOOST_INSTALL_FLAGS=--force run _engine_install pass
  [ "$status" -eq 0 ]
  grep -q 'install -y pass' "${STUB_DNF_LOG}"
}
@test "pass: unsupported-OS — no install command on non-fedora" {
  run _module_install_cmd pass ubuntu debian
  [ -z "$output" ]
}

@test "pass-store: generates a passphrase-less GPG key when none exists, then pass init" {
  run _run_passstore
  [ "$status" -eq 0 ]
  grep -q -- '--quick-generate-key' "${STUB_GPG_LOG}"
  grep -q 'pass init' "${STUB_PASS_LOG}"
  [ -f "${PASSWORD_STORE_DIR}/.gpg-id" ]
}
@test "pass-store: does NOT regenerate the key when one already exists" {
  export STUB_GPG_KEYS=1
  run _run_passstore
  [ "$status" -eq 0 ]
  ! grep -q -- '--quick-generate-key' "${STUB_GPG_LOG}"
  grep -q 'pass init' "${STUB_PASS_LOG}"
}
@test "pass-store: clones DEVBOOST_PASS_REPO into the store when set" {
  export DEVBOOST_PASS_REPO="git@example.com:me/pw.git"
  run _run_passstore
  [ "$status" -eq 0 ]
  grep -q "clone git@example.com:me/pw.git" "${STUB_GIT_LOG}"
}
@test "pass-store: verify RED before, GREEN after; idempotent re-run" {
  run _run_verify
  [ "$status" -ne 0 ]
  _run_passstore
  run _run_verify
  [ "$status" -eq 0 ]
  # idempotent: re-run with key present + store initialized → no regen, no error
  export STUB_GPG_KEYS=1
  run _run_passstore
  [ "$status" -eq 0 ]
}
@test "pass-store: module metadata — requires pass + secrets" {
  grep -q 'requires    = \["pass", "secrets"\]' "${DEVBOOST_ROOT}/modules/pass-store/module.toml"
}
