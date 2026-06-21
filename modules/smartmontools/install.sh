#!/usr/bin/env bash
# modules/smartmontools/install.sh — install smartmontools + enable smartd.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "smartmontools: installing"
dnf_install smartmontools

log_info "smartmontools: enabling smartd"
sudo systemctl enable smartd

log_ok "smartmontools: ready"
