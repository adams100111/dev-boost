# lib/secrets.sh — locate, decrypt, and expose the age-encrypted secret bundle.
# Source-only library; sourcing has NO side effects (defines functions only).
# Depends on: lib/log.sh (die, log_error, log_info), jq, age.

# ---------------------------------------------------------------------------
# have <cmd>
#   Return 0 if <cmd> is found on PATH, non-zero otherwise.
# ---------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# ensure_pkg <pkg-name> <install-cmd>
#   Run <install-cmd> only when <pkg-name> is not on PATH.
# ---------------------------------------------------------------------------
ensure_pkg() {
  local pkg="$1"; shift
  if ! have "${pkg}"; then
    log_info "secrets: installing ${pkg}"
    bash -c "$*"
  fi
}

# ---------------------------------------------------------------------------
# secrets_bundle_path
#   Resolve the path to the encrypted bundle (does not decrypt).
#   Precedence: DEVBOOST_SECRETS → default ($DEVBOOST_BOOTSTRAP_DIR/secrets.age).
#   Prints the resolved path to stdout.
#   Exits 0 if the file exists, 1 if it does not.
# ---------------------------------------------------------------------------
secrets_bundle_path() {
  local path
  if [[ -n "${DEVBOOST_SECRETS:-}" ]]; then
    path="${DEVBOOST_SECRETS}"
  else
    local bootstrap_dir="${DEVBOOST_BOOTSTRAP_DIR:-${DEVBOOST_ROOT}}"
    path="${bootstrap_dir}/secrets.age"
  fi
  printf '%s\n' "${path}"
  [[ -f "${path}" ]]
}

# ---------------------------------------------------------------------------
# secrets_decrypt
#   Decrypt the bundle and emit valid JSON to stdout.
#   Exits:
#     0  — success, JSON on stdout
#     2  — bundle file missing
#     3  — age decryption failed (bad/missing key)
#     4  — decrypted output is not valid JSON
# ---------------------------------------------------------------------------
secrets_decrypt() {
  # Locate bundle.
  local bundle
  bundle="$(secrets_bundle_path)" || {
    log_error "secrets bundle not found: ${bundle}"
    return 2
  }

  # Locate key file.
  local key="${DEVBOOST_SECRETS_KEY:-}"
  if [[ -z "${key}" ]]; then
    local bootstrap_dir="${DEVBOOST_BOOTSTRAP_DIR:-${DEVBOOST_ROOT}}"
    key="${bootstrap_dir}/age-key.txt"
  fi

  # Decrypt; capture both stdout and stderr (stderr goes to /dev/null, errors via status).
  local json
  json="$(age -d -i "${key}" "${bundle}" 2>/dev/null)" || {
    log_error "cannot decrypt secrets bundle"
    return 3
  }

  # Validate JSON.
  if ! printf '%s' "${json}" | jq -e . >/dev/null 2>&1; then
    log_error "secrets: invalid JSON in decrypted bundle"
    return 4
  fi

  printf '%s\n' "${json}"
}

# ---------------------------------------------------------------------------
# secrets_get <KEY>
#   Return the value of KEY from the decrypted bundle (stdout).
#   Exits 5 if the key is absent or empty.
# ---------------------------------------------------------------------------
secrets_get() {
  local key="$1"
  local json value
  json="$(secrets_decrypt)" || return $?

  value="$(printf '%s' "${json}" | jq -r --arg k "${key}" '.[$k] // empty')"
  if [[ -z "${value}" ]]; then
    log_error "secrets: missing required field ${key}"
    return 5
  fi
  printf '%s\n' "${value}"
}

# ---------------------------------------------------------------------------
# secrets_user   → GIT_USER
# secrets_email  → GIT_EMAIL
# secrets_pat    → GITHUB_PAT  (value printed to stdout ONLY — never logged)
# ---------------------------------------------------------------------------
secrets_user()  { secrets_get GIT_USER; }
secrets_email() { secrets_get GIT_EMAIL; }
secrets_pat()   { secrets_get GITHUB_PAT; }
