#!/usr/bin/env bash
# modules/fwupd/install.sh — install fwupd + enable the firmware update daemon.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "fwupd: installing"
dnf_install fwupd

log_info "fwupd: enabling fwupd.service"
sudo systemctl enable fwupd.service

log_ok "fwupd: ready"
