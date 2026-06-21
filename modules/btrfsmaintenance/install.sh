#!/usr/bin/env bash
# modules/btrfsmaintenance/install.sh — install btrfsmaintenance + enable timers.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: install btrfsmaintenance.
# ---------------------------------------------------------------------------
log_info "btrfsmaintenance: installing"
dnf_install btrfsmaintenance

# ---------------------------------------------------------------------------
# Step 2: enable the scrub + balance maintenance timers.
# ---------------------------------------------------------------------------
log_info "btrfsmaintenance: enabling scrub + balance timers"
sudo systemctl enable btrfs-scrub.timer
sudo systemctl enable btrfs-balance.timer

log_ok "btrfsmaintenance: ready"
