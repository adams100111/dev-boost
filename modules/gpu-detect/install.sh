#!/usr/bin/env bash
# modules/gpu-detect/install.sh — detect GPU vendor and record a driver-path selection.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (rewrites the marker deterministically); non-interactive.
#
# This module installs NO driver packages. NVIDIA hardware ⇒ it records the
# "nvidia" selection and recommends the `hardware-nvidia` profile (which carries
# the actual nvidia-akmod/cuda/etc. packages). Intel/AMD ⇒ the open path.
#
# Verify (END state): the marker file exists and is non-empty (see verify.sh).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/gpu.sh"

# Marker recording the selected GPU driver path (override for tests).
GPU_MARKER="${DEVBOOST_GPU_MARKER:-${DEVBOOST_ROOT}/workstation-config/gpu.selected}"

log_info "gpu-detect: detecting GPU vendor(s) via lspci"
gpu_detect              # sets GPU_VENDORS + GPU_UNRECOGNIZED
_vendors="${GPU_VENDORS}"

# Report unrecognized hardware (FR-009) — never silently drop it.
if [[ -n "${GPU_UNRECOGNIZED// /}" ]]; then
  log_warn "gpu-detect: unrecognized GPU vendor(s):${GPU_UNRECOGNIZED}"
fi

if [[ -z "${_vendors// /}" && -z "${GPU_UNRECOGNIZED// /}" ]]; then
  die "gpu-detect: no GPU controller found via lspci — cannot record a selection"
fi

# Decide the driver path: NVIDIA present ⇒ "nvidia"; otherwise ⇒ "open".
_selection="open"
if [[ " ${_vendors} " == *" nvidia "* ]]; then
  _selection="nvidia"
fi

# Write the marker deterministically (idempotent).
mkdir -p "$(dirname "${GPU_MARKER}")"
printf '%s\n' "${_selection}" > "${GPU_MARKER}" \
  || die "gpu-detect: could not write marker ${GPU_MARKER}"

if [[ "${_selection}" == "nvidia" ]]; then
  log_ok "gpu-detect: NVIDIA GPU detected — selected the 'hardware-nvidia' driver path (run with --profile hardware-nvidia to install NVIDIA packages)"
else
  log_ok "gpu-detect: selected the open driver path (vendors:${_vendors:- none})"
fi
