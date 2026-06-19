# tests/fixtures/secrets/stubs.bash — shared bats stub harness for secrets-and-auth tests.
#
# Source this file in a bats test file via:
#   load fixtures/secrets/stubs
#
# It provides:
#   stubs_setup       — call in bats setup()   : installs PATH stubs + scratch HOME
#   stubs_teardown    — call in bats teardown() : cleans up temp dirs
#   stubs_stub_dir    — path to the temp bin directory prepended to PATH
#   stubs_home_dir    — path to the scratch HOME used by tests
#
# Individual install helpers (called by stubs_setup; may be called independently):
#   stubs_install_age       — install age stub into stub bin dir
#   stubs_install_curl      — install curl stub + init call-log
#   stubs_install_ssh_keygen — install ssh-keygen stub into stub bin dir
#
# Env knobs (set before calling stubs_setup or the relevant install helper):
#   STUB_AGE_FAIL=1       — age stub exits 1 (simulates bad key / decrypt failure)
#   STUB_CURL_STATUS      — HTTP status the curl stub returns (default: 200)
#   STUB_CURL_BODY        — raw body override for curl stub (bypasses URL-keyed canned responses)
#   STUB_CURL_LOG         — path to the curl invocation log (default: $BATS_TEST_TMPDIR/curl-calls.log)
#
# All stubs write no real network traffic; all temp files live under BATS_TEST_TMPDIR
# or $BATS_SUITE_TMPDIR and are cleaned up by bats automatically or by stubs_teardown.

# _stubs_fixture_dir resolves the absolute path to this stubs directory.
_stubs_fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# _stubs_bundle_json is the path to the fixture JSON bundle the age stub outputs.
_stubs_bundle_json="${_stubs_fixture_dir}/bundle.json"

# ---------------------------------------------------------------------------
# stubs_setup — main entry point; creates scratch dirs, installs all stubs.
# ---------------------------------------------------------------------------
stubs_setup() {
  # Create a temp bin directory for stub executables.
  _stubs_bin_dir="$(mktemp -d)"
  # Create a scratch HOME so tests never touch the real home.
  _stubs_home_dir="$(mktemp -d)"

  # Prepend stub bin dir to PATH so our fakes shadow real tools.
  export PATH="${_stubs_bin_dir}:${PATH}"

  # Export scratch HOME and XDG dirs for isolation.
  export HOME="${_stubs_home_dir}"
  export XDG_STATE_HOME="${_stubs_home_dir}/.local/state"
  mkdir -p "${_stubs_home_dir}/.local/state/devboost"

  # Wire DEVBOOST_SECRETS* env vars to the fixture bundle.
  export DEVBOOST_SECRETS="${_stubs_fixture_dir}/bundle.json"
  # DEVBOOST_SECRETS_KEY points at a fake (non-existent) key; the age stub ignores it.
  export DEVBOOST_SECRETS_KEY="${_stubs_home_dir}/age-key.txt"
  export DEVBOOST_BOOTSTRAP_DIR="${_stubs_fixture_dir}"

  # Default curl call-log path (tests can override STUB_CURL_LOG before calling stubs_setup).
  export STUB_CURL_LOG="${STUB_CURL_LOG:-${BATS_TEST_TMPDIR}/curl-calls.log}"
  : > "${STUB_CURL_LOG}"   # ensure file exists and is empty

  stubs_install_age
  stubs_install_curl
  stubs_install_ssh_keygen
}

# ---------------------------------------------------------------------------
# stubs_teardown — remove temp dirs created by stubs_setup.
# ---------------------------------------------------------------------------
stubs_teardown() {
  # Remove stub bin dir (bats also cleans BATS_TEST_TMPDIR, but be explicit).
  [[ -n "${_stubs_bin_dir:-}" && -d "${_stubs_bin_dir}" ]] && rm -rf "${_stubs_bin_dir}"
  [[ -n "${_stubs_home_dir:-}" && -d "${_stubs_home_dir}" ]] && rm -rf "${_stubs_home_dir}"
}

# ---------------------------------------------------------------------------
# stubs_stub_dir / stubs_home_dir — accessors for use in test assertions.
# ---------------------------------------------------------------------------
stubs_stub_dir() { printf '%s\n' "${_stubs_bin_dir}"; }
stubs_home_dir()  { printf '%s\n' "${_stubs_home_dir}"; }

# ---------------------------------------------------------------------------
# stubs_install_age — write a fake `age` binary to the stub bin dir.
#
# Behaviour:
#   age -d ...  → prints the fixture bundle.json to stdout; exits 0
#                 OR exits 1 when STUB_AGE_FAIL=1 (simulates bad key)
#   (any other invocation form is silently ignored / exits 0)
# ---------------------------------------------------------------------------
stubs_install_age() {
  cat > "${_stubs_bin_dir}/age" <<'STUB'
#!/usr/bin/env bash
# Stub: age — fake age decryptor for bats tests.
if [[ "${STUB_AGE_FAIL:-0}" == "1" ]]; then
  printf 'age: error: wrong key or corrupted file\n' >&2
  exit 1
fi
# On -d flag (decrypt mode), emit the fixture bundle.
if [[ "$*" == *"-d"* ]]; then
  cat "${DEVBOOST_SECRETS:-${DEVBOOST_BOOTSTRAP_DIR}/bundle.json}"
fi
exit 0
STUB
  chmod +x "${_stubs_bin_dir}/age"
}

# ---------------------------------------------------------------------------
# stubs_install_curl — write a fake `curl` binary to the stub bin dir.
#
# The stub:
#  - Appends the full argument list (one space-separated line) to STUB_CURL_LOG.
#  - Returns STUB_CURL_BODY (if set) or a canned response keyed by the URL and
#    HTTP method derived from the argument list.
#  - Exits with a status that reflects STUB_CURL_STATUS (default 0/200 → success).
#
# Canned responses (used when STUB_CURL_BODY is not overridden):
#   GET  /user/keys              → empty key list (no existing keys)
#   POST /user/keys              → created key object (id:1)
#   GET  /repos/*/keys           → empty deploy-key list
#   POST /repos/*/keys           → created deploy-key object (id:2)
#   (any other URL)              → {"message":"Not Found"}  with status 404
#
# For duplicate-detection tests, set STUB_CURL_BODY to a JSON array containing
# a key entry before calling the function under test.
#
# The stub writes HTTP 2xx on success (status 200/201) and the configured
# STUB_CURL_STATUS code otherwise. lib/github.sh uses -w '%{http_code}' and
# reads the last token as the status. The stub appends the HTTP code as the
# last line of output to match that convention.
# ---------------------------------------------------------------------------
stubs_install_curl() {
  cat > "${_stubs_bin_dir}/curl" <<'STUB'
#!/usr/bin/env bash
# Stub: curl — fake HTTP client for bats tests.
# Logs every call; returns canned GitHub API responses.

log_file="${STUB_CURL_LOG:-/tmp/stub-curl-calls.log}"
# Append argument list to the call log (one line per invocation).
printf '%s\n' "$*" >> "${log_file}"

# Determine request method and URL from args.
method="GET"
url=""
for i in "$@"; do
  case "$prev" in
    -X|--request) method="$i" ;;
    -H|--header)  : ;;  # skip header values
    *)
      # First non-flag, non-value argument that looks like a URL.
      if [[ "$i" == https://* && -z "$url" ]]; then
        url="$i"
      fi
      ;;
  esac
  prev="$i"
done

http_status="${STUB_CURL_STATUS:-200}"

if [[ -n "${STUB_CURL_BODY:-}" ]]; then
  body="${STUB_CURL_BODY}"
else
  # Route by URL path + method to canned responses.
  path="${url#*api.github.com}"
  case "${method}:${path}" in
    GET:/user/keys)
      body='[]'
      ;;
    POST:/user/keys)
      body='{"id":1,"title":"devboost:testhost","key":"ssh-ed25519 AAAA fake-pub-key"}'
      http_status="${STUB_CURL_STATUS:-201}"
      ;;
    GET:/repos/*/keys)
      body='[]'
      ;;
    POST:/repos/*/keys)
      body='{"id":2,"title":"devboost:testhost","key":"ssh-ed25519 AAAA fake-pub-key","read_only":false}'
      http_status="${STUB_CURL_STATUS:-201}"
      ;;
    *)
      body='{"message":"Not Found"}'
      http_status="${STUB_CURL_STATUS:-404}"
      ;;
  esac
fi

# lib/github.sh calls curl with -w '\n%{http_code}' to capture status separately.
# Emit body then the HTTP code on a new line so the caller can strip the last token.
printf '%s\n%s\n' "${body}" "${http_status}"
exit 0
STUB
  chmod +x "${_stubs_bin_dir}/curl"
}

# ---------------------------------------------------------------------------
# stubs_install_ssh_keygen — write a fake `ssh-keygen` binary to the stub bin dir.
#
# Behaviour:
#   ssh-keygen -t ed25519 -f <path> ...
#     → writes a deterministic fake private key to <path>
#     → writes a deterministic fake public key to <path>.pub
#   (The -N flag for empty passphrase is accepted and ignored.)
# ---------------------------------------------------------------------------
stubs_install_ssh_keygen() {
  cat > "${_stubs_bin_dir}/ssh-keygen" <<'STUB'
#!/usr/bin/env bash
# Stub: ssh-keygen — writes deterministic fake ed25519 key pair.
keyfile=""
# Parse -f <path> from arguments.
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f) keyfile="$2"; shift 2 ;;
    *)  shift ;;
  esac
done

if [[ -z "${keyfile}" ]]; then
  printf 'ssh-keygen stub: -f <keyfile> is required\n' >&2
  exit 1
fi

# Write a deterministic fake private key (OpenSSH format placeholder).
cat > "${keyfile}" <<'PRIVKEY'
-----BEGIN OPENSSH PRIVATE KEY-----
STUB_FAKE_ED25519_PRIVATE_KEY_FOR_TESTING_ONLY_NOT_REAL
-----END OPENSSH PRIVATE KEY-----
PRIVKEY
chmod 600 "${keyfile}"

# Write a deterministic fake public key.
printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5STUB_FAKE_PUBKEY_FOR_TESTING devboost-test\n' \
  > "${keyfile}.pub"
chmod 644 "${keyfile}.pub"

exit 0
STUB
  chmod +x "${_stubs_bin_dir}/ssh-keygen"
}

# ---------------------------------------------------------------------------
# stubs_curl_log — print the path to the curl call-log (for assertions).
# ---------------------------------------------------------------------------
stubs_curl_log() { printf '%s\n' "${STUB_CURL_LOG}"; }

# ---------------------------------------------------------------------------
# stubs_assert_no_pat_in_log — helper: assert the PAT does not appear in logs.
# Typically called after a function that uses curl or logs to check FR-012/FR-013.
# Usage:  stubs_assert_no_pat_in_log <log-file> <pat-value>
# ---------------------------------------------------------------------------
stubs_assert_no_pat_in_log() {
  local logfile="$1" pat="$2"
  if grep -qF "${pat}" "${logfile}" 2>/dev/null; then
    printf 'ASSERTION FAILED: PAT found in log file %s\n' "${logfile}" >&2
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# stubs_with_duplicate_keys — configure curl stub to return a list with an
# existing key (for testing duplicate-detection / idempotency paths).
#
# Usage:
#   stubs_with_duplicate_keys <title> <pubkey-body>
#   (export STUB_CURL_BODY so the curl stub returns it for the next GET /user/keys)
# ---------------------------------------------------------------------------
stubs_with_duplicate_keys() {
  local title="$1" key_body="$2"
  export STUB_CURL_BODY="[{\"id\":99,\"title\":\"${title}\",\"key\":\"${key_body}\"}]"
}

# ---------------------------------------------------------------------------
# stubs_with_http_error — configure curl stub to return a specific HTTP error
# status for all subsequent calls (resets STUB_CURL_BODY to a generic error).
#
# Usage:
#   stubs_with_http_error 422
# ---------------------------------------------------------------------------
stubs_with_http_error() {
  local status="$1"
  export STUB_CURL_STATUS="${status}"
  export STUB_CURL_BODY="{\"message\":\"Validation Failed\",\"status\":${status}}"
}
