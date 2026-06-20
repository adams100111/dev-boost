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
# Step 1: install starship via dnf (primary path on Fedora).
# The official installer (curl sh.starship.rs | sh) is the fallback but
# requires network access; dnf is preferred for reproducibility.
# ---------------------------------------------------------------------------
log_info "starship: installing via dnf"
sudo dnf install -y starship

log_ok "starship: binary installed"
