#!/usr/bin/env bash
# modules/snapper-dnf-hook/install.sh — install the DNF↔snapper transaction plugin.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "snapper-dnf-hook: installing python3-dnf-plugin-snapper"
dnf_install python3-dnf-plugin-snapper

log_ok "snapper-dnf-hook: ready"
