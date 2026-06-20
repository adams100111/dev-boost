#!/usr/bin/env bash
# modules/chezmoi/install.sh — install chezmoi and adopt dotfiles repo.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# Requires: secrets module (git credential store seeded by secrets).
# No prompts; idempotent (safe to re-run). Clone failure is non-blocking.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure chezmoi is installed
# ---------------------------------------------------------------------------
need_cmd chezmoi chezmoi

# ---------------------------------------------------------------------------
# Step 2: chezmoi init — adopt config directory
# ---------------------------------------------------------------------------
log_info "chezmoi: running chezmoi init to adopt config"
if chezmoi init; then
  log_ok "chezmoi: init succeeded"
else
  log_warn "chezmoi: init/clone failed — dotfiles not synced (non-blocking)"
  return 0 2>/dev/null || exit 0
fi

log_ok "chezmoi: setup complete"
