#!/usr/bin/env bash
# modules/libva-nvidia-driver/install.sh — NVIDIA VA-API driver (Spec 10, FR-006).
# Package renamed from nvidia-vaapi-driver to libva-nvidia-driver. Fedora-only;
# idempotent (verify-guarded); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "libva-nvidia-driver: installing libva-nvidia-driver"
dnf_install libva-nvidia-driver

log_ok "libva-nvidia-driver: NVIDIA VA-API driver installed"
