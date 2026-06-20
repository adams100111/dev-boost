#!/usr/bin/env bash
# modules/dotfiles/install.sh — apply dev-boost curated dotfiles via chezmoi.
# Sourced env: DEVBOOST_ROOT, HOME.
# No prompts; idempotent (chezmoi apply replaces managed files, never appends).
# Secrets are never written by this module (FR-014).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

# ---------------------------------------------------------------------------
# Resolve source directory (this repo's dotfiles/).
# The --source override makes dev-boost's tree authoritative, independent of
# any user DEVBOOST_DOTFILES_REPO clone managed by the base chezmoi module.
# ---------------------------------------------------------------------------
_dotfiles_src="${DEVBOOST_ROOT}/dotfiles"

if [[ ! -d "${_dotfiles_src}" ]]; then
  log_error "dotfiles: source directory not found: ${_dotfiles_src}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Apply: chezmoi replaces managed files (idempotent; no append → no duplicate
# init lines).  FR-007/FR-009.
# ---------------------------------------------------------------------------
log_info "dotfiles: applying chezmoi source from ${_dotfiles_src}"

if ! chezmoi apply --source "${_dotfiles_src}" --destination "${HOME}"; then
  log_error "dotfiles: chezmoi apply failed (source=${_dotfiles_src})"
  exit 1
fi

log_ok "dotfiles: managed configs applied to ${HOME}"
