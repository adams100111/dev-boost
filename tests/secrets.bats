load test_helper
load fixtures/secrets/stubs

# DEVBOOST_ROOT is set by test_helper; expose it for the source cmd in subshells.

setup() {
  stubs_setup
  load_lib log.sh
  source "${DEVBOOST_ROOT}/lib/secrets.sh"
}

teardown() {
  stubs_teardown
}

# ---------------------------------------------------------------------------
# Helper: source secrets.sh inside a subshell for run-based tests.
# ---------------------------------------------------------------------------
_src() {
  printf 'source "%s/lib/log.sh"; source "%s/lib/secrets.sh"; ' \
    "${DEVBOOST_ROOT}" "${DEVBOOST_ROOT}"
}

# ---------------------------------------------------------------------------
# secrets_bundle_path — precedence tests
# ---------------------------------------------------------------------------

@test "secrets_bundle_path: returns DEVBOOST_SECRETS when set" {
  run bash -c "$(_src) secrets_bundle_path"
  [ "$status" -eq 0 ]
  [ "$output" = "${DEVBOOST_SECRETS}" ]
}

@test "secrets_bundle_path: falls back to default when DEVBOOST_SECRETS unset" {
  local default_path="${DEVBOOST_BOOTSTRAP_DIR}/secrets.age"
  run bash -c "
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    unset DEVBOOST_SECRETS
    $(_src) secrets_bundle_path"
  # exit 1 when file doesn't exist at default path; path is still printed
  [[ "$output" == *"secrets.age"* ]]
}

@test "secrets_bundle_path: exits 1 when bundle missing" {
  run bash -c "
    unset DEVBOOST_SECRETS
    export DEVBOOST_BOOTSTRAP_DIR='/nonexistent/path'
    $(_src) secrets_bundle_path"
  [ "$status" -eq 1 ]
}

# ---------------------------------------------------------------------------
# secrets_decrypt — happy path + error paths
# ---------------------------------------------------------------------------

@test "secrets_decrypt: happy path emits valid JSON with required keys" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_decrypt"
  [ "$status" -eq 0 ]
  # Output must be parseable JSON
  printf '%s' "$output" | jq -e . >/dev/null
  [[ "$output" == *"GIT_USER"* ]]
  [[ "$output" == *"GIT_EMAIL"* ]]
  [[ "$output" == *"GITHUB_PAT"* ]]
}

@test "secrets_decrypt: exits 2 when bundle is missing" {
  run bash -c "
    export DEVBOOST_SECRETS='/nonexistent/secrets.age'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_decrypt"
  [ "$status" -eq 2 ]
  [[ "$output" == *"secrets bundle not found"* ]]
}

@test "secrets_decrypt: exits 3 when age decryption fails" {
  run bash -c "
    export STUB_AGE_FAIL=1
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_decrypt"
  [ "$status" -eq 3 ]
  [[ "$output" == *"cannot decrypt secrets bundle"* ]]
}

@test "secrets_decrypt: exits 4 on invalid JSON output" {
  # Create a temp file that age stub will emit (not valid JSON)
  local bad_bundle
  bad_bundle="$(mktemp)"
  printf 'this is not json at all\n' > "${bad_bundle}"

  run bash -c "
    export DEVBOOST_SECRETS='${bad_bundle}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_decrypt"
  [ "$status" -eq 4 ]
  [[ "$output" == *"invalid JSON"* ]]
  rm -f "${bad_bundle}"
}

# ---------------------------------------------------------------------------
# secrets_get — happy path + missing field
# ---------------------------------------------------------------------------

@test "secrets_get: returns value for existing key" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_get GIT_USER"
  [ "$status" -eq 0 ]
  [ "$output" = "devboost-test-user" ]
}

@test "secrets_get: exits 5 for missing field" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_get NONEXISTENT_KEY"
  [ "$status" -eq 5 ]
  [[ "$output" == *"missing required field"* ]]
  [[ "$output" == *"NONEXISTENT_KEY"* ]]
}

# ---------------------------------------------------------------------------
# secrets_user / secrets_email / secrets_pat — convenience wrappers
# ---------------------------------------------------------------------------

@test "secrets_user: returns GIT_USER value" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_user"
  [ "$status" -eq 0 ]
  [ "$output" = "devboost-test-user" ]
}

@test "secrets_email: returns GIT_EMAIL value" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_email"
  [ "$status" -eq 0 ]
  [ "$output" = "devboost-test@example.com" ]
}

@test "secrets_pat: returns GITHUB_PAT value" {
  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_pat"
  [ "$status" -eq 0 ]
  [ "$output" = "ghp_TESTfaketoken0000000000000000000001" ]
}

# ---------------------------------------------------------------------------
# PAT must NOT appear in log/stderr output
# ---------------------------------------------------------------------------

@test "secrets_pat: PAT does not appear in stderr/log output" {
  local pat="ghp_TESTfaketoken0000000000000000000001"
  local logfile
  logfile="$(mktemp)"

  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_pat 2>'${logfile}'"

  # stdout: PAT is expected there (it's the return value)
  # stderr/logfile: PAT must NOT appear
  stubs_assert_no_pat_in_log "${logfile}" "${pat}"
  rm -f "${logfile}"
}

@test "secrets_decrypt: PAT does not appear in stderr" {
  local pat="ghp_TESTfaketoken0000000000000000000001"
  local logfile
  logfile="$(mktemp)"

  run bash -c "
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export PATH='${PATH}'
    $(_src) secrets_decrypt 2>'${logfile}'"

  stubs_assert_no_pat_in_log "${logfile}" "${pat}"
  rm -f "${logfile}"
}

# ---------------------------------------------------------------------------
# have — command existence check
# ---------------------------------------------------------------------------

@test "have: returns 0 for a command that exists" {
  run bash -c "$(_src) have jq"
  [ "$status" -eq 0 ]
}

@test "have: returns non-zero for a command that does not exist" {
  run bash -c "$(_src) have totally_nonexistent_cmd_xyz"
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# ensure_pkg — installs only when command absent
# ---------------------------------------------------------------------------

@test "ensure_pkg: runs install cmd when command is absent" {
  local marker
  marker="$(mktemp)"
  rm -f "${marker}"   # ensure it doesn't exist yet

  run bash -c "
    export PATH='${PATH}'
    $(_src) ensure_pkg totally_nonexistent_cmd_xyz 'touch ${marker}'"
  # install cmd should have been called
  [ -f "${marker}" ]
  rm -f "${marker}"
}

@test "ensure_pkg: skips install cmd when command already present" {
  local marker
  marker="$(mktemp)"
  rm -f "${marker}"   # ensure clean state

  # jq is present, so the install cmd should NOT run
  run bash -c "
    export PATH='${PATH}'
    $(_src) ensure_pkg jq 'touch ${marker}'"
  [ "$status" -eq 0 ]
  # marker should NOT exist because jq is present
  [ ! -f "${marker}" ]
  rm -f "${marker}"
}

# ---------------------------------------------------------------------------
# T006: modules/secrets/install.sh — install behavior tests
# ---------------------------------------------------------------------------

# Helper: run install.sh in a subshell with all required env exported.
_run_install_sh() {
  bash \
    -c "
      export HOME='${HOME}'
      export PATH='${PATH}'
      export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
      export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
      export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
      export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
      export OS_DISTRO='fedora'
      export OS_FAMILY='fedora'
      export OS_ARCH='x86_64'
      bash '${DEVBOOST_ROOT}/modules/secrets/install.sh'
    " 2>&1
}

@test "secrets module: install sets git user.name from bundle" {
  _run_install_sh
  run git config --global user.name
  [ "$status" -eq 0 ]
  [ "$output" = "devboost-test-user" ]
}

@test "secrets module: install sets git user.email from bundle" {
  _run_install_sh
  run git config --global user.email
  [ "$status" -eq 0 ]
  [ "$output" = "devboost-test@example.com" ]
}

@test "secrets module: install sets credential.helper to store" {
  _run_install_sh
  run git config --global credential.helper
  [ "$status" -eq 0 ]
  [ "$output" = "store" ]
}

@test "secrets module: install writes ~/.git-credentials with github.com line" {
  _run_install_sh
  [ -f "${HOME}/.git-credentials" ]
  grep -q '@github.com' "${HOME}/.git-credentials"
}

@test "secrets module: ~/.git-credentials has mode 600" {
  _run_install_sh
  local perms
  perms="$(stat -c '%a' "${HOME}/.git-credentials")"
  [ "$perms" = "600" ]
}

@test "secrets module: second run does NOT duplicate the github.com line" {
  _run_install_sh
  _run_install_sh
  local count
  count="$(grep -c '@github.com' "${HOME}/.git-credentials")"
  [ "$count" -eq 1 ]
}

@test "secrets module: missing bundle field causes failure naming the field" {
  # Create a bundle missing GITHUB_PAT
  local bad_bundle
  bad_bundle="$(mktemp)"
  printf '{"GIT_USER":"alice","GIT_EMAIL":"alice@example.com"}\n' > "${bad_bundle}"

  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${bad_bundle}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/secrets/install.sh'
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"GITHUB_PAT"* ]]
  rm -f "${bad_bundle}"
}

@test "secrets module: PAT never appears in stdout or stderr" {
  local pat="ghp_TESTfaketoken0000000000000000000001"
  local output_log
  output_log="$(mktemp)"

  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/secrets/install.sh'
  " >"${output_log}" 2>&1

  stubs_assert_no_pat_in_log "${output_log}" "${pat}"
  rm -f "${output_log}"
}

@test "secrets module: verify string returns success after install" {
  _run_install_sh
  local vcmd='git config --global user.email >/dev/null 2>&1 && [ -f "$HOME/.git-credentials" ] && grep -q '"'"'@github.com'"'"' "$HOME/.git-credentials"'
  run bash -c "export HOME='${HOME}'; ${vcmd}"
  [ "$status" -eq 0 ]
}

@test "secrets module: verify string fails before install" {
  # Fresh scratch HOME, nothing installed yet
  local vcmd='git config --global user.email >/dev/null 2>&1 && [ -f "$HOME/.git-credentials" ] && grep -q '"'"'@github.com'"'"' "$HOME/.git-credentials"'
  run bash -c "export HOME='${HOME}'; ${vcmd}"
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# T009: end-to-end idempotency via the real engine
# ---------------------------------------------------------------------------

@test "engine e2e: first run installs secrets module (ok status)" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_ROOT}/modules'
    export DEVBOOST_PROFILES='${DEVBOOST_ROOT}/tests/fixtures/secrets/profiles.toml'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    '${DEVBOOST_ROOT}/bin/devboost' install secrets
  " 2>&1
  [ "$status" -eq 0 ]
  [[ "$output" == *"secrets"* ]]
}

@test "engine e2e: second run skips secrets module (verify-guard)" {
  # First run: install
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_ROOT}/modules'
    export DEVBOOST_PROFILES='${DEVBOOST_ROOT}/tests/fixtures/secrets/profiles.toml'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    '${DEVBOOST_ROOT}/bin/devboost' install secrets
  " 2>&1

  # Second run: should skip
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_ROOT}/modules'
    export DEVBOOST_PROFILES='${DEVBOOST_ROOT}/tests/fixtures/secrets/profiles.toml'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    '${DEVBOOST_ROOT}/bin/devboost' install secrets
  " 2>&1
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}
