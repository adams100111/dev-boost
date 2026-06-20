#!/usr/bin/env bash
# modules/ghostty/install.sh — install Ghostty terminal via COPR.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
#
# Ghostty is available via the scottames/ghostty COPR repository on Fedora.
# Ptyxis is intentionally left available as the GNOME default terminal fallback.
# This module adds the COPR repo (skip-if-already-enabled) then installs ghostty.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: enable the scottames/ghostty COPR repository if not already present.
# Check first; only run `copr enable` when the COPR is absent so the operation
# is strictly add-if-absent (mirrors rpmfusion/docker module pattern).
# ---------------------------------------------------------------------------
if dnf copr list 2>/dev/null | grep -q 'scottames/ghostty'; then
  log_info "ghostty: scottames/ghostty COPR already enabled — skipping"
else
  log_info "ghostty: enabling scottames/ghostty COPR"
  sudo dnf copr enable -y scottames/ghostty
fi

# ---------------------------------------------------------------------------
# Step 2: install ghostty from the COPR repository.
# ---------------------------------------------------------------------------
log_info "ghostty: installing ghostty package"
sudo dnf install -y ghostty

# Note: Ptyxis is NOT removed — it remains available as the GNOME fallback
# terminal emulator. Users who prefer Ghostty can set it as their default
# without losing Ptyxis.

log_ok "ghostty: installed via scottames/ghostty COPR"
