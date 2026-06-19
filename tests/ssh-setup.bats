load test_helper
load fixtures/secrets/stubs

# DEVBOOST_ROOT is set by test_helper.

setup() {
  stubs_setup
  load_lib log.sh
}

teardown() {
  stubs_teardown
}

# ---------------------------------------------------------------------------
# Helper: source prefix for subshell tests.
# ---------------------------------------------------------------------------
_src_ssh() {
  printf 'source "%s/lib/log.sh"; source "%s/lib/secrets.sh"; source "%s/lib/github.sh"; ' \
    "${DEVBOOST_ROOT}" "${DEVBOOST_ROOT}" "${DEVBOOST_ROOT}"
}

# ---------------------------------------------------------------------------
# Helper: run install.sh in a subshell with all required env exported.
# ---------------------------------------------------------------------------
_run_install_sh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: state marker path.
# ---------------------------------------------------------------------------
_marker_path() {
  printf '%s' "${XDG_STATE_HOME}/devboost/ssh-key-registered"
}

# ---------------------------------------------------------------------------
# T012 — Key generation
# ---------------------------------------------------------------------------

@test "ssh-setup: generates ed25519 key when none exists" {
  run _run_install_sh
  [ -f "${HOME}/.ssh/id_ed25519" ]
  [ -f "${HOME}/.ssh/id_ed25519.pub" ]
}

@test "ssh-setup: does NOT overwrite an existing private key (FR-005)" {
  # Pre-create a key with sentinel content.
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  printf 'EXISTING_SENTINEL_PRIVATE_KEY\n' > "${HOME}/.ssh/id_ed25519"
  chmod 600 "${HOME}/.ssh/id_ed25519"
  printf 'ssh-ed25519 EXISTING_SENTINEL_PUBKEY existing\n' > "${HOME}/.ssh/id_ed25519.pub"
  chmod 644 "${HOME}/.ssh/id_ed25519.pub"

  _run_install_sh

  # Private key content must be unchanged.
  run grep -q 'EXISTING_SENTINEL_PRIVATE_KEY' "${HOME}/.ssh/id_ed25519"
  [ "$status" -eq 0 ]
}

@test "ssh-setup: ~/.ssh directory has mode 700" {
  _run_install_sh
  local perms
  perms="$(stat -c '%a' "${HOME}/.ssh")"
  [ "${perms}" = "700" ]
}

@test "ssh-setup: private key has mode 600" {
  _run_install_sh
  local perms
  perms="$(stat -c '%a' "${HOME}/.ssh/id_ed25519")"
  [ "${perms}" = "600" ]
}

# ---------------------------------------------------------------------------
# T012 — ~/.ssh/config hardened block
# ---------------------------------------------------------------------------

@test "ssh-setup: ~/.ssh/config contains IdentityFile entry" {
  _run_install_sh
  grep -q 'IdentityFile' "${HOME}/.ssh/config"
}

@test "ssh-setup: ~/.ssh/config contains IdentitiesOnly yes" {
  _run_install_sh
  grep -q 'IdentitiesOnly yes' "${HOME}/.ssh/config"
}

@test "ssh-setup: ~/.ssh/config contains AddKeysToAgent yes" {
  _run_install_sh
  grep -q 'AddKeysToAgent yes' "${HOME}/.ssh/config"
}

@test "ssh-setup: ~/.ssh/config contains HashKnownHosts yes" {
  _run_install_sh
  grep -q 'HashKnownHosts yes' "${HOME}/.ssh/config"
}

@test "ssh-setup: ~/.ssh/config block is idempotent (no duplication on second run)" {
  _run_install_sh
  _run_install_sh
  # Count occurrences of the begin marker — must be exactly 1.
  local count
  count="$(grep -c 'BEGIN devboost' "${HOME}/.ssh/config")"
  [ "${count}" -eq 1 ]
}

@test "ssh-setup: ~/.ssh/config block is idempotent (IdentityFile not duplicated)" {
  _run_install_sh
  _run_install_sh
  local count
  count="$(grep -c 'IdentityFile' "${HOME}/.ssh/config")"
  [ "${count}" -eq 1 ]
}

@test "ssh-setup: no block duplication when pre-existing BEGIN marker has trailing whitespace" {
  # Seed ~/.ssh/config with a BEGIN marker that has a trailing space — the old
  # exact-match awk ($0 == begin) would miss it and append a second block.
  # The regex-based awk must detect and replace it, leaving exactly one block.
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  # Write the config with a trailing space on the BEGIN marker line.
  printf '# BEGIN devboost-managed \nHost *\n  IdentityFile ~/.ssh/id_rsa\n  IdentitiesOnly yes\n# END devboost-managed\n' \
    > "${HOME}/.ssh/config"

  # Run install twice — both runs must detect the existing block and replace it.
  _run_install_sh
  _run_install_sh

  local count
  count="$(grep -cE '^# BEGIN devboost-managed' "${HOME}/.ssh/config")"
  [ "${count}" -eq 1 ]
}

# ---------------------------------------------------------------------------
# T012 — State marker
# ---------------------------------------------------------------------------

@test "ssh-setup: state marker is written after successful upload" {
  _run_install_sh
  [ -f "$(_marker_path)" ]
}

@test "ssh-setup: state marker is NOT written when upload fails (FR-007)" {
  stubs_with_http_error 422

  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='${STUB_CURL_STATUS}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " 2>&1
  # install.sh returns 0 even on upload failure
  [ "$status" -eq 0 ]
  # Marker must NOT exist
  [ ! -f "$(_marker_path)" ]
}

@test "ssh-setup: install.sh returns 0 even when upload fails (non-blocking, FR-007)" {
  stubs_with_http_error 422

  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='${STUB_CURL_STATUS}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "ssh-setup: install.sh logs a warning on upload failure" {
  stubs_with_http_error 422

  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='${STUB_CURL_STATUS}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " 2>&1
  # bats merges stderr into $output — log_warn emits '[!]'; must appear in output.
  # This will fail if log_warn is regressed to log_info ('[*]').
  [[ "$output" == *"[!]"* ]]
}

# ---------------------------------------------------------------------------
# T012 — verify string
# ---------------------------------------------------------------------------

@test "ssh-setup: verify string is GREEN after successful install" {
  _run_install_sh
  local vcmd
  vcmd='[ -f "$HOME/.ssh/id_ed25519.pub" ] && [ -f "${XDG_STATE_HOME:-$HOME/.local/state}/devboost/ssh-key-registered" ]'
  run bash -c "
    export HOME='${HOME}'
    export XDG_STATE_HOME='${XDG_STATE_HOME}'
    ${vcmd}
  "
  [ "$status" -eq 0 ]
}

@test "ssh-setup: verify string is RED before install" {
  local vcmd
  vcmd='[ -f "$HOME/.ssh/id_ed25519.pub" ] && [ -f "${XDG_STATE_HOME:-$HOME/.local/state}/devboost/ssh-key-registered" ]'
  run bash -c "
    export HOME='${HOME}'
    export XDG_STATE_HOME='${XDG_STATE_HOME}'
    ${vcmd}
  "
  [ "$status" -ne 0 ]
}

@test "ssh-setup: verify string is RED when marker absent (upload failed)" {
  stubs_with_http_error 422

  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='${STUB_CURL_STATUS}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " 2>&1

  # pubkey exists but marker does not — verify must be red
  local vcmd
  vcmd='[ -f "$HOME/.ssh/id_ed25519.pub" ] && [ -f "${XDG_STATE_HOME:-$HOME/.local/state}/devboost/ssh-key-registered" ]'
  run bash -c "
    export HOME='${HOME}'
    export XDG_STATE_HOME='${XDG_STATE_HOME}'
    ${vcmd}
  "
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# T012 — Security: PAT and private key never in stdout/stderr
# ---------------------------------------------------------------------------

@test "ssh-setup: PAT never appears in stdout or stderr" {
  local pat
  pat="$(jq -r .GITHUB_PAT "${DEVBOOST_ROOT}/tests/fixtures/secrets/bundle.json")"
  local output_log
  output_log="$(mktemp)"

  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " >"${output_log}" 2>&1

  stubs_assert_no_pat_in_log "${output_log}" "${pat}"
  rm -f "${output_log}"
}

@test "ssh-setup: private key content never appears in stdout or stderr" {
  local output_log
  output_log="$(mktemp)"

  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export DEVBOOST_BOOTSTRAP_DIR='${DEVBOOST_BOOTSTRAP_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_API='https://api.github.com'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export OS_ARCH='x86_64'
    bash '${DEVBOOST_ROOT}/modules/ssh-setup/install.sh'
  " >"${output_log}" 2>&1

  # The fake private key content is 'STUB_FAKE_ED25519_PRIVATE_KEY_FOR_TESTING_ONLY_NOT_REAL'
  if grep -q 'STUB_FAKE_ED25519_PRIVATE_KEY' "${output_log}" 2>/dev/null; then
    printf 'ASSERTION FAILED: private key content found in output log\n' >&2
    rm -f "${output_log}"
    return 1
  fi
  rm -f "${output_log}"
}
