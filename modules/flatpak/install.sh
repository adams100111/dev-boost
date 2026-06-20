#!/usr/bin/env bash
# modules/flatpak/install.sh — install Flatpak, add Flathub, unfilter Fedora default.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine + flatpak_remote_add skip); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure flatpak is installed.
# ---------------------------------------------------------------------------
need_cmd flatpak flatpak

# ---------------------------------------------------------------------------
# Step 2: add the Flathub remote (skip-when-present via flatpak_remote_add).
# ---------------------------------------------------------------------------
flatpak_remote_add flathub "https://flathub.org/repo/flathub.flatpakrepo"

# ---------------------------------------------------------------------------
# Step 3: remove Fedora's default filter on the flathub remote so all
# applications are visible (not just the Fedora-curated subset).
# ---------------------------------------------------------------------------
log_info "flatpak: removing Fedora filter from flathub remote"
flatpak remote-modify --no-filter flathub

log_ok "flatpak: Flathub remote configured (unfiltered)"
