#!/usr/bin/env bash
# modules/chezmoi-repo/install.sh — chezmoi init + clone of the remote dotfiles repo.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME. Requires: chezmoi, secrets.
# Clone uses ~/.git-credentials seeded by secrets; no token on the command line.
# No prompts; idempotent; clone failure is non-blocking.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if [[ -n "${DEVBOOST_DOTFILES_REPO:-}" ]]; then
  log_info "chezmoi-repo: cloning dotfiles from ${DEVBOOST_DOTFILES_REPO} (via credential store)"
  if chezmoi init --apply "${DEVBOOST_DOTFILES_REPO}"; then
    log_ok "chezmoi-repo: dotfiles cloned and applied"
  else
    log_warn "chezmoi-repo: init/clone failed — dotfiles not synced (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
else
  log_info "chezmoi-repo: DEVBOOST_DOTFILES_REPO not set — running local init (no clone)"
  if chezmoi init; then
    log_ok "chezmoi-repo: local init succeeded"
  else
    log_warn "chezmoi-repo: local init failed (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
fi

log_ok "chezmoi-repo: setup complete"
