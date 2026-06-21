#!/usr/bin/env bash
# modules/gpu-detect/verify.sh — idempotency guard for the gpu-detect module.
# GREEN iff a GPU driver-path selection has been recorded (marker exists, non-empty).
# No prompts; read-only.
set -Eeuo pipefail

GPU_MARKER="${DEVBOOST_GPU_MARKER:-${DEVBOOST_ROOT}/workstation-config/gpu.selected}"

[[ -s "${GPU_MARKER}" ]] || exit 1
exit 0
