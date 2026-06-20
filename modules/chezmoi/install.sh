#!/usr/bin/env bash
# modules/chezmoi/install.sh — install chezmoi and adopt dotfiles repo.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# Requires: secrets module (git credential store seeded by secrets).
# Clone uses ~/.git-credentials set by secrets; no token on the command line.
# No prompts; idempotent (safe to re-run). Clone failure is non-blocking.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure chezmoi is installed
# ---------------------------------------------------------------------------
need_cmd chezmoi chezmoi

# ---------------------------------------------------------------------------
# Step 2: chezmoi init — clone dotfiles repo if configured, else local init
# ---------------------------------------------------------------------------
if [[ -n "${DEVBOOST_DOTFILES_REPO:-}" ]]; then
  log_info "chezmoi: cloning dotfiles from ${DEVBOOST_DOTFILES_REPO} (via credential store)"
  # chezmoi init --apply <repo> clones over HTTPS and applies immediately.
  # Credentials come from ~/.git-credentials (seeded by the secrets module).
  # NEVER put a token or credential on the command line.
  if chezmoi init --apply "${DEVBOOST_DOTFILES_REPO}"; then
    log_ok "chezmoi: dotfiles cloned and applied"
  else
    log_warn "chezmoi: init/clone failed — dotfiles not synced (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
else
  log_info "chezmoi: DEVBOOST_DOTFILES_REPO not set — running local init (no clone)"
  if chezmoi init; then
    log_ok "chezmoi: local init succeeded"
  else
    log_warn "chezmoi: local init failed (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
fi

log_ok "chezmoi: setup complete"
