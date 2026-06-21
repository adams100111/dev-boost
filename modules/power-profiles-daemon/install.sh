#!/usr/bin/env bash
# modules/power-profiles-daemon/install.sh — install + enable power-profiles-daemon.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "power-profiles-daemon: installing"
dnf_install power-profiles-daemon

log_info "power-profiles-daemon: enabling service"
sudo systemctl enable power-profiles-daemon

log_ok "power-profiles-daemon: ready"
