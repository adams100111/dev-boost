load test_helper
load fixtures/secrets/stubs

setup() {
  stubs_setup
  load_lib log.sh
  source "${DEVBOOST_ROOT}/lib/github.sh"
  # Set PAT in env so functions can pick it up
  export GITHUB_PAT="ghp_TESTfaketoken0000000000000000000001"
  # GITHUB_API must stay at default so the stub URL routing (strips api.github.com) works
  export GITHUB_API="https://api.github.com"
}

teardown() {
  stubs_teardown
}

# ---------------------------------------------------------------------------
# Helper: build a source prefix for subshell tests.
# ---------------------------------------------------------------------------
_src_gh() {
  printf 'source "%s/lib/log.sh"; source "%s/lib/github.sh"; ' \
    "${DEVBOOST_ROOT}" "${DEVBOOST_ROOT}"
}

# ---------------------------------------------------------------------------
# Helper: write a deterministic fake public key file.
# ---------------------------------------------------------------------------
_write_pubkey() {
  local path="$1"
  printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5STUB_FAKE_PUBKEY_FOR_TESTING devboost-test\n' \
    > "${path}"
}

# ---------------------------------------------------------------------------
# gh_api — header assertions
# ---------------------------------------------------------------------------

@test "gh_api: sends Authorization: Bearer header (via header file)" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys >/dev/null
  " 2>&1
  # The call-log must reference a header file (using -H @<path> mechanism) so
  # the PAT is never exposed in the argument list.  The @ prefix is the marker.
  grep -qE -- '-H @' "${STUB_CURL_LOG}"
}

@test "gh_api: sends Accept: application/vnd.github+json header" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys >/dev/null
  " 2>&1
  grep -q 'application/vnd.github+json' "${STUB_CURL_LOG}"
}

@test "gh_api: sends X-GitHub-Api-Version: 2022-11-28 header" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys >/dev/null
  " 2>&1
  grep -q '2022-11-28' "${STUB_CURL_LOG}"
}

@test "gh_api: returns 0 on HTTP 2xx response" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "gh_api: returns 1 on HTTP non-2xx response" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='403'
    export STUB_CURL_BODY='{\"message\":\"Forbidden\"}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys
  " 2>&1
  [ "$status" -eq 1 ]
}

@test "gh_api: logs parsed .message on non-2xx failure" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='422'
    export STUB_CURL_BODY='{\"message\":\"Validation Failed\"}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api POST /user/keys '{}'
  " 2>&1
  [[ "$output" == *"Validation Failed"* ]]
}

# ---------------------------------------------------------------------------
# gh_upload_ssh_key — new key path (POST once)
# ---------------------------------------------------------------------------

@test "gh_upload_ssh_key: POSTs exactly once for a new key" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:newtesthost'
  " 2>&1
  [ "$status" -eq 0 ]
  # Count POST /user/keys lines in the call-log
  local post_count
  post_count="$(grep -c 'POST' "${STUB_CURL_LOG}" || true)"
  [ "${post_count}" -eq 1 ]
}

# ---------------------------------------------------------------------------
# gh_upload_ssh_key — idempotency: title match skips POST
# ---------------------------------------------------------------------------

@test "gh_upload_ssh_key: skips POST when title already exists on remote" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  # Configure stub to return existing key with matching title
  stubs_with_duplicate_keys "devboost:newtesthost" "ssh-ed25519 DIFFERENT_KEY devboost-test"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:newtesthost'
  " 2>&1
  [ "$status" -eq 0 ]
  # No POST should have been made
  local post_count
  post_count="$(grep -c 'POST' "${STUB_CURL_LOG}" || true)"
  [ "${post_count}" -eq 0 ]
}

# ---------------------------------------------------------------------------
# gh_upload_ssh_key — idempotency: key body match skips POST
# ---------------------------------------------------------------------------

@test "gh_upload_ssh_key: skips POST when key body already exists on remote" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"
  local key_body
  key_body="$(cat "${pubkey}")"
  # Strip trailing newline from key body for JSON matching
  key_body="${key_body%$'\n'}"

  # Configure stub to return existing key with different title but same key body
  stubs_with_duplicate_keys "devboost:otherhost" "${key_body}"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:newtesthost'
  " 2>&1
  [ "$status" -eq 0 ]
  # No POST should have been made
  local post_count
  post_count="$(grep -c 'POST' "${STUB_CURL_LOG}" || true)"
  [ "${post_count}" -eq 0 ]
}

# ---------------------------------------------------------------------------
# gh_upload_ssh_key — HTTP error path
# ---------------------------------------------------------------------------

@test "gh_upload_ssh_key: returns non-zero on HTTP error during upload" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  stubs_with_http_error 422

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_STATUS='${STUB_CURL_STATUS}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:newtesthost'
  " 2>&1
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# gh_add_deploy_key — posts with read_only field
# ---------------------------------------------------------------------------

@test "gh_add_deploy_key: POSTs with read_only=true when --read-only flag given" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_add_deploy_key 'myowner' 'myrepo' '${pubkey}' 'devboost:testhost' --read-only
  " 2>&1
  [ "$status" -eq 0 ]
  # POST must have been made
  local post_count
  post_count="$(grep -c 'POST' "${STUB_CURL_LOG}" || true)"
  [ "${post_count}" -eq 1 ]
  # The POST body must contain read_only:true
  grep -q 'true' "${STUB_CURL_LOG}"
}

@test "gh_add_deploy_key: POSTs with read_only=false by default" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_add_deploy_key 'myowner' 'myrepo' '${pubkey}' 'devboost:testhost'
  " 2>&1
  [ "$status" -eq 0 ]
  grep -q 'false' "${STUB_CURL_LOG}"
}

@test "gh_add_deploy_key: skips POST when title already registered as deploy key" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"

  stubs_with_duplicate_keys "devboost:testhost" "ssh-ed25519 DIFFERENT_BODY devboost-test"

  run bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CURL_BODY='${STUB_CURL_BODY}'
    export GITHUB_PAT='ghp_TESTfaketoken0000000000000000000001'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_add_deploy_key 'myowner' 'myrepo' '${pubkey}' 'devboost:testhost'
  " 2>&1
  [ "$status" -eq 0 ]
  local post_count
  post_count="$(grep -c 'POST' "${STUB_CURL_LOG}" || true)"
  [ "${post_count}" -eq 0 ]
}

# ---------------------------------------------------------------------------
# PAT never appears in curl call-log or any log line (FR-006, FR-013)
# ---------------------------------------------------------------------------

@test "gh_api: PAT never appears in curl call-log" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"
  local pat="ghp_TESTfaketoken0000000000000000000001"

  bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='${pat}'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_api GET /user/keys >/dev/null
  " 2>&1

  stubs_assert_no_pat_in_log "${STUB_CURL_LOG}" "${pat}"
}

@test "gh_upload_ssh_key: PAT never appears in curl call-log" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"
  local pat="ghp_TESTfaketoken0000000000000000000001"

  bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='${pat}'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:testhost' >/dev/null
  " 2>&1

  stubs_assert_no_pat_in_log "${STUB_CURL_LOG}" "${pat}"
}

@test "gh_upload_ssh_key: PAT never appears in log output" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"
  local pat="ghp_TESTfaketoken0000000000000000000001"
  local logfile="${BATS_TEST_TMPDIR}/stderr.log"

  bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='${pat}'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_upload_ssh_key '${pubkey}' 'devboost:testhost'
  " 2>"${logfile}"

  stubs_assert_no_pat_in_log "${logfile}" "${pat}"
}

@test "gh_add_deploy_key: PAT never appears in curl call-log" {
  local pubkey="${BATS_TEST_TMPDIR}/id_ed25519.pub"
  _write_pubkey "${pubkey}"
  local pat="ghp_TESTfaketoken0000000000000000000001"

  bash -c "
    export PATH='${PATH}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export GITHUB_PAT='${pat}'
    export GITHUB_API='https://api.github.com'
    $(_src_gh)
    gh_add_deploy_key 'myowner' 'myrepo' '${pubkey}' 'devboost:testhost' >/dev/null
  " 2>&1

  stubs_assert_no_pat_in_log "${STUB_CURL_LOG}" "${pat}"
}
