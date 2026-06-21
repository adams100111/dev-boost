#!/usr/bin/env bash
# modules/nvidia-container-toolkit/install.sh — GPU access for Docker (Spec 10, FR-010).
# Fedora-only; idempotent (verify-guarded); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "nvidia-container-toolkit: installing nvidia-container-toolkit"
dnf_install nvidia-container-toolkit

log_info "nvidia-container-toolkit: configuring the Docker runtime (nvidia-ctk runtime configure)"
sudo nvidia-ctk runtime configure --runtime=docker

log_ok "nvidia-container-toolkit: GPU container runtime configured"
