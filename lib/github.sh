# lib/github.sh — PAT-authenticated GitHub REST helpers. Source-only; no side effects.
# Depends on: lib/log.sh (log_info, log_warn, log_error), curl, jq.
#
# Auth: GITHUB_PAT env var (or pass explicitly via callers).
# All requests include:
#   Authorization: Bearer <PAT>
#   Accept: application/vnd.github+json
#   X-GitHub-Api-Version: 2022-11-28
#
# Base URL: GITHUB_API (default: https://api.github.com)

GITHUB_API="${GITHUB_API:-https://api.github.com}"

# ---------------------------------------------------------------------------
# gh_api <METHOD> <path> [json-body]
#   Run curl against the GitHub REST API with auth headers.
#   Stdout: response body (without the trailing HTTP status line).
#   Exit:   0 on HTTP 2xx; 1 on non-2xx (logs parsed .message; never leaks PAT).
# ---------------------------------------------------------------------------
gh_api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local pat="${GITHUB_PAT:-}"
  local url="${GITHUB_API}${path}"

  # Write the Authorization header to a temp file so the PAT never appears in
  # the argument list (which is logged by the test stub and potentially by ps/audit).
  local auth_header_file
  auth_header_file="$(mktemp)"
  # shellcheck disable=SC2064
  trap "rm -f '${auth_header_file}'" RETURN
  printf 'Authorization: Bearer %s\n' "${pat}" > "${auth_header_file}"

  local curl_args=(
    -s
    -X "${method}"
    -H "@${auth_header_file}"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28"
    -w '\n%{http_code}'
  )

  if [[ -n "${body}" ]]; then
    curl_args+=(-H "Content-Type: application/json" -d "${body}")
  fi

  curl_args+=("${url}")

  # Capture full output: body lines + trailing HTTP status line.
  local raw
  raw="$(curl "${curl_args[@]}")"

  # The stub (and real curl with -w '\n%{http_code}') appends the HTTP code as the last line.
  local http_status
  http_status="${raw##*$'\n'}"
  local response_body
  response_body="${raw%$'\n'*}"

  if [[ "${http_status}" =~ ^2 ]]; then
    printf '%s\n' "${response_body}"
    return 0
  else
    local msg
    msg="$(printf '%s' "${response_body}" | jq -r '.message // "unknown error"' 2>/dev/null \
      || printf 'unknown error')"
    log_error "GitHub API ${method} ${path} failed (HTTP ${http_status}): ${msg}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# gh_upload_ssh_key <pubkey-file> <title>
#   Register a public SSH key under the authenticated user's account.
#   Idempotent: skips POST if the title OR key body already exists remotely.
#   Exit: 0 on success / already-registered; 1 on API failure.
# ---------------------------------------------------------------------------
gh_upload_ssh_key() {
  local pubkey_file="$1"
  local title="$2"

  local key_body
  key_body="$(cat "${pubkey_file}")"
  # Trim trailing newline for comparison with API response values.
  key_body="${key_body%$'\n'}"

  # GET existing keys and check for duplicates.
  local existing
  existing="$(gh_api GET /user/keys)" || return 1

  # Check for duplicate title.
  local dup_title
  dup_title="$(printf '%s' "${existing}" | \
    jq -r --arg t "${title}" '.[] | select(.title == $t) | .title' 2>/dev/null)"
  if [[ -n "${dup_title}" ]]; then
    log_info "github: SSH key already registered (title match): ${title}"
    return 0
  fi

  # Check for duplicate key body.
  local dup_key
  dup_key="$(printf '%s' "${existing}" | \
    jq -r --arg k "${key_body}" '.[] | select(.key == $k) | .key' 2>/dev/null)"
  if [[ -n "${dup_key}" ]]; then
    log_info "github: SSH key already registered (key body match)"
    return 0
  fi

  # No duplicate found — POST the new key.
  local payload
  payload="$(jq -n --arg t "${title}" --arg k "${key_body}" \
    '{"title": $t, "key": $k}')"
  gh_api POST /user/keys "${payload}" >/dev/null || return 1
  log_ok "github: SSH key registered: ${title}"
}

# ---------------------------------------------------------------------------
# gh_add_deploy_key <owner> <repo> <pubkey-file> <title> [--read-only]
#   Register a deploy key on the given repository.
#   Idempotent: skips POST if the title OR key body already exists.
#   Exit: 0 on success / already-registered; 1 on API failure.
# ---------------------------------------------------------------------------
gh_add_deploy_key() {
  local owner="$1"
  local repo="$2"
  local pubkey_file="$3"
  local title="$4"
  local read_only="false"
  if [[ "${5:-}" == "--read-only" ]]; then
    read_only="true"
  fi

  local key_body
  key_body="$(cat "${pubkey_file}")"
  key_body="${key_body%$'\n'}"

  local keys_path="/repos/${owner}/${repo}/keys"

  # GET existing deploy keys and check for duplicates.
  local existing
  existing="$(gh_api GET "${keys_path}")" || return 1

  # Check for duplicate title.
  local dup_title
  dup_title="$(printf '%s' "${existing}" | \
    jq -r --arg t "${title}" '.[] | select(.title == $t) | .title' 2>/dev/null)"
  if [[ -n "${dup_title}" ]]; then
    log_info "github: deploy key already registered (title match): ${title}"
    return 0
  fi

  # Check for duplicate key body.
  local dup_key
  dup_key="$(printf '%s' "${existing}" | \
    jq -r --arg k "${key_body}" '.[] | select(.key == $k) | .key' 2>/dev/null)"
  if [[ -n "${dup_key}" ]]; then
    log_info "github: deploy key already registered (key body match)"
    return 0
  fi

  # POST the new deploy key.
  local payload
  payload="$(jq -n --arg t "${title}" --arg k "${key_body}" --argjson ro "${read_only}" \
    '{"title": $t, "key": $k, "read_only": $ro}')"
  gh_api POST "${keys_path}" "${payload}" >/dev/null || return 1
  log_ok "github: deploy key registered on ${owner}/${repo}: ${title}"
}
