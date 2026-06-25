#!/usr/bin/env bash
# modules/chezmoi/install.sh — install the chezmoi binary ONLY (portable).
# Init/clone of the remote dotfiles repo lives in the chezmoi-repo module.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME. Idempotent.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if command -v chezmoi >/dev/null 2>&1; then
  log_skip "chezmoi: binary already installed"
else
  log_info "chezmoi: installing binary"
  mkdir -p "${HOME}/.local/bin"
  # Official installer; OS-agnostic; no prompts; pins into ~/.local/bin.
  sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "${HOME}/.local/bin"
  log_ok "chezmoi: binary installed"
fi
