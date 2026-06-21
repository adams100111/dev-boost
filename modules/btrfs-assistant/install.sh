#!/usr/bin/env bash
# modules/btrfs-assistant/install.sh — install the Btrfs Assistant GUI.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "btrfs-assistant: installing"
dnf_install btrfs-assistant

log_ok "btrfs-assistant: ready"
