#!/usr/bin/env bash
# modules/vscode/install.sh — install VS Code from the Microsoft dnf repo and the
# curated baseline extension set. Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# Optional: DEVBOOST_YUM_REPOS_DIR (defaults to /etc/yum.repos.d) so tests need no root.
# No prompts; idempotent (engine verify-guarded); non-interactive.
#
# Why the MS repo (not a sandboxed app): it yields the native `code` CLI, which is
# required for headless extension provisioning (`code --install-extension` /
# `--list-extensions`) and for the editor's tooling to see the mise-managed PATH.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

YUM_REPOS_DIR="${DEVBOOST_YUM_REPOS_DIR:-/etc/yum.repos.d}"
REPO_FILE="${YUM_REPOS_DIR}/vscode.repo"
MS_KEY="https://packages.microsoft.com/keys/microsoft.asc"

# ---------------------------------------------------------------------------
# Step 1: import the Microsoft signing key + write the vscode.repo (idempotent).
# ---------------------------------------------------------------------------
log_info "vscode: importing Microsoft signing key"
sudo rpm --import "${MS_KEY}"

if [[ -f "${REPO_FILE}" ]] && grep -q '^\[code\]' "${REPO_FILE}" 2>/dev/null; then
  log_skip "vscode: ${REPO_FILE} already present"
else
  log_info "vscode: writing ${REPO_FILE}"
  sudo mkdir -p "${YUM_REPOS_DIR}"
  sudo tee "${REPO_FILE}" >/dev/null <<EOF
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
autorefresh=1
type=rpm-md
gpgcheck=1
gpgkey=${MS_KEY}
EOF
fi

# ---------------------------------------------------------------------------
# Step 2: install the `code` package.
# ---------------------------------------------------------------------------
log_info "vscode: installing code"
dnf_install code

# ---------------------------------------------------------------------------
# Step 3: install only the curated baseline extensions that are missing.
# Run as the invoking user (not root) so extensions land in the user profile.
# ---------------------------------------------------------------------------
ext_file="${DEVBOOST_ROOT}/modules/vscode/extensions.txt"
[[ -f "${ext_file}" ]] || die "vscode: extension list not found: ${ext_file}"

installed="$(code --list-extensions 2>/dev/null || true)"

while IFS= read -r ext || [[ -n "${ext}" ]]; do
  [[ -z "${ext}" || "${ext}" == \#* ]] && continue
  if grep -qxF "${ext}" <<<"${installed}"; then
    log_skip "vscode: extension already installed: ${ext}"
  else
    log_info "vscode: installing extension ${ext}"
    code --install-extension "${ext}" --force
  fi
done < "${ext_file}"

log_ok "vscode: installed with curated baseline extensions"
