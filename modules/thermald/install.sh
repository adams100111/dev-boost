#!/usr/bin/env bash
# modules/thermald/install.sh — install + enable thermald.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "thermald: installing"
dnf_install thermald

log_info "thermald: enabling service"
sudo systemctl enable thermald

log_ok "thermald: ready"
