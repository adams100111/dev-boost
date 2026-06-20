#!/usr/bin/env bash
# modules/secrets/install.sh — configure git identity + HTTPS credentials.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (safe to re-run).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/secrets.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure age is available
# ---------------------------------------------------------------------------
case "${OS_DISTRO:-${OS_FAMILY:-}}" in
  fedora|rhel|centos)
    ensure_pkg age "sudo dnf install -y age"
    ;;
  debian|ubuntu)
    ensure_pkg age "sudo apt-get install -y age"
    ;;
  macos|darwin)
    ensure_pkg age "brew install age"
    ;;
  *)
    # Best-effort fallback — covers unknown distros on a fedora-family system.
    ensure_pkg age "sudo dnf install -y age" \
      || ensure_pkg age "sudo apt-get install -y age" \
      || { die "secrets: age not available and no known install method for ${OS_DISTRO:-unknown}"; }
    ;;
esac

have age || die "secrets: age is required but could not be installed"

# ---------------------------------------------------------------------------
# Step 2: decrypt the bundle
# ---------------------------------------------------------------------------
json="$(secrets_decrypt)" || {
  log_error "secrets: failed to decrypt bundle (exit $?)"
  exit 1
}

# ---------------------------------------------------------------------------
# Step 3: extract required fields — fail immediately if any is missing
# ---------------------------------------------------------------------------
_field() {
  local key="$1"
  local val
  val="$(printf '%s' "${json}" | jq -r --arg k "${key}" '.[$k] // empty')"
  if [[ -z "${val}" ]]; then
    die "secrets: missing required field ${key}"
  fi
  printf '%s' "${val}"
}

GIT_USER="$(_field GIT_USER)"
GIT_EMAIL="$(_field GIT_EMAIL)"
GITHUB_PAT="$(_field GITHUB_PAT)"

# ---------------------------------------------------------------------------
# Step 4: configure git identity and credential helper
# ---------------------------------------------------------------------------
git config --global user.name  "${GIT_USER}"
git config --global user.email "${GIT_EMAIL}"
git config --global credential.helper store
log_info "secrets: git identity configured (${GIT_EMAIL})"

# ---------------------------------------------------------------------------
# Step 5: write ~/.git-credentials (replace existing github.com line; chmod 600)
# ---------------------------------------------------------------------------
creds_file="${HOME}/.git-credentials"
new_line="https://${GIT_USER}:${GITHUB_PAT}@github.com"

# Ensure the file exists and is mode 600 before writing.
touch "${creds_file}"
chmod 600 "${creds_file}"

# Remove any pre-existing github.com line (replace-not-append idempotency).
# Use a temp file for atomic replacement so no partial writes occur.
tmp_creds="$(mktemp)"
trap 'rm -f "${tmp_creds}"' EXIT
grep -v '@github\.com$' "${creds_file}" > "${tmp_creds}" || true
printf '%s\n' "${new_line}" >> "${tmp_creds}"
chmod 600 "${tmp_creds}"
mv "${tmp_creds}" "${creds_file}"

log_ok "secrets: credentials written to ${creds_file}"
