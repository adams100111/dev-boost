#!/usr/bin/env bash
# modules/gh/install.sh — install GitHub CLI via official dnf repo.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (safe to re-run).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: add GitHub CLI dnf repo if not already present
# ---------------------------------------------------------------------------
_gh_repo_marker="${XDG_CONFIG_HOME:-${HOME}/.config}/gh-cli.repo"
if [[ ! -f "${_gh_repo_marker}" ]]; then
  log_info "gh: adding GitHub CLI repository"
  sudo dnf config-manager --add-repo \
    https://cli.github.com/packages/rpm/gh-cli.repo
  touch "${_gh_repo_marker}"
  log_ok "gh: repository added"
else
  log_skip "gh: repository already configured"
fi

# ---------------------------------------------------------------------------
# Step 2: install gh
# ---------------------------------------------------------------------------
log_info "gh: installing"
sudo dnf install -y gh

log_ok "gh: installation complete"
