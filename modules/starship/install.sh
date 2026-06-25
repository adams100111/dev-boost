#!/usr/bin/env bash
# modules/starship/install.sh — install Starship cross-shell prompt binary.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
#
# IMPORTANT: This module installs the binary ONLY.
# The `eval "$(starship init bash)"` init line is managed by the dotfiles
# module (CS-WI5) and lives in the chezmoi-managed ~/.bashrc — it is NOT
# written here.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: install starship binary.
# Fedora fast-path: dnf (preferred for reproducibility).
# All other OS: official starship.rs installer into ~/.local/bin.
# ---------------------------------------------------------------------------
log_info "starship: installing binary"
if command -v starship >/dev/null 2>&1; then
  log_skip "starship: already installed"
elif [[ "${OS_FAMILY}" == "fedora" ]]; then
  sudo dnf install -y starship
else
  # Official installer; OS-agnostic; -y non-interactive; into ~/.local/bin.
  mkdir -p "${HOME}/.local/bin"
  curl -sS https://starship.rs/install.sh | sh -s -- -y -b "${HOME}/.local/bin"
fi
log_ok "starship: binary installed"
