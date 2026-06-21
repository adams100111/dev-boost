#!/usr/bin/env bash
# modules/cuda/install.sh — NVIDIA CUDA userspace (Spec 10, FR-006). Fedora-only;
# idempotent (verify-guarded); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "cuda: installing xorg-x11-drv-nvidia-cuda"
dnf_install xorg-x11-drv-nvidia-cuda

log_ok "cuda: CUDA userspace installed"
