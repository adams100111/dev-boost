#!/usr/bin/env bash
# modules/ddev/install.sh — install ddev, the container-based Laravel/PHP dev
# orchestrator, from its official Fedora dnf repo. Sourced env: DEVBOOST_ROOT,
# OS_DISTRO, OS_FAMILY, HOME.
# Optional: DEVBOOST_YUM_REPOS_DIR (defaults to /etc/yum.repos.d) so tests need no root.
# No prompts; idempotent (engine verify-guarded + skip-if-present); non-interactive.
#
# Why ddev (not host php/composer): every Laravel project runs inside ddev's
# containers, so the host needs only the orchestrator. PHP, Composer and the web
# server live in the project's containers — keeping the host clean and reproducible.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# Already installed — nothing to do (idempotent fast path).
if have ddev; then
  log_skip "ddev: already installed"
  exit 0
fi

YUM_REPOS_DIR="${DEVBOOST_YUM_REPOS_DIR:-/etc/yum.repos.d}"
REPO_FILE="${YUM_REPOS_DIR}/ddev.repo"

# ---------------------------------------------------------------------------
# Step 1: write the ddev.repo (idempotent — only if absent).
# ---------------------------------------------------------------------------
if [[ -f "${REPO_FILE}" ]]; then
  log_skip "ddev: ${REPO_FILE} already present"
else
  log_info "ddev: writing ${REPO_FILE}"
  sudo mkdir -p "${YUM_REPOS_DIR}"
  sudo tee "${REPO_FILE}" >/dev/null <<'EOF'
[ddev]
name=ddev
baseurl=https://pkg.ddev.com/yum/
gpgcheck=0
enabled=1
EOF
fi

# ---------------------------------------------------------------------------
# Step 2: install ddev (refresh metadata so the freshly-added repo is seen).
# ---------------------------------------------------------------------------
log_info "ddev: installing ddev"
sudo dnf install --refresh -y ddev

# ---------------------------------------------------------------------------
# Step 3: trust ddev's local CA so HTTPS dev URLs work (idempotent).
# ---------------------------------------------------------------------------
log_info "ddev: trusting local CA via mkcert"
mkcert -install

log_ok "ddev: installed (Laravel/PHP runs in containers; no host php/composer)"
