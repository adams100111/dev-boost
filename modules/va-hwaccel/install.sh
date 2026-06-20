#!/usr/bin/env bash
# modules/va-hwaccel/install.sh — GPU-aware VA-API hardware acceleration driver install.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
# Verify (END state): vainfo exits 0 (reports a working driver).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: install libva-utils (provides vainfo — the VA-API end-state oracle).
# ---------------------------------------------------------------------------
log_info "va-hwaccel: installing libva-utils"
dnf_install libva-utils

# ---------------------------------------------------------------------------
# Step 2: detect GPU vendor(s) from lspci.
# Lines matching VGA/3D/Display controller are GPU candidates.
# ---------------------------------------------------------------------------
_gpu_lines="$(lspci | grep -E '(VGA compatible controller|3D controller|Display controller)')"

_has_intel=0
_has_amd=0
_has_nvidia=0
_unrecognized_vendors=""

while IFS= read -r line; do
  [[ -z "${line}" ]] && continue
  # Use whole-word matching (-w) to avoid false positives.
  # "compatible" contains "ati" and "Corporation" contains "ati" — word boundaries prevent mismatches.
  if echo "${line}" | grep -qwi "Intel"; then
    _has_intel=1
  elif echo "${line}" | grep -qwiE "AMD|ATI"; then
    _has_amd=1
  elif echo "${line}" | grep -qwi "NVIDIA"; then
    _has_nvidia=1
  else
    # Extract the vendor/device portion (after the PCI address and controller type).
    _vendor_part="$(echo "${line}" | sed 's/^[0-9a-f:.]*[[:space:]]*//' | sed 's/.*controller:[[:space:]]*//')"
    _unrecognized_vendors="${_unrecognized_vendors} ${_vendor_part}"
  fi
done <<< "${_gpu_lines}"

# ---------------------------------------------------------------------------
# Step 3: guard — unrecognized vendor means we can't install a driver safely.
# ---------------------------------------------------------------------------
if [[ -n "${_unrecognized_vendors// /}" && "${_has_intel}" -eq 0 && "${_has_amd}" -eq 0 && "${_has_nvidia}" -eq 0 ]]; then
  die "va-hwaccel: unrecognized GPU vendor(s):${_unrecognized_vendors} — cannot install VA-API driver automatically"
fi

# ---------------------------------------------------------------------------
# Step 4: install per-vendor driver(s).  Hybrid = run ALL matched actions.
# ---------------------------------------------------------------------------
if [[ "${_has_intel}" -eq 1 ]]; then
  log_info "va-hwaccel: Intel GPU detected — installing intel-media-driver"
  dnf_install intel-media-driver
fi

if [[ "${_has_amd}" -eq 1 ]]; then
  log_info "va-hwaccel: AMD/ATI GPU detected — swapping mesa drivers to freeworld variants"
  sudo dnf swap -y mesa-va-drivers mesa-va-drivers-freeworld
  sudo dnf swap -y mesa-vdpau-drivers mesa-vdpau-drivers-freeworld
fi

if [[ "${_has_nvidia}" -eq 1 ]]; then
  log_info "va-hwaccel: NVIDIA GPU detected — installing libva-nvidia-driver"
  dnf_install libva-nvidia-driver
fi

# ---------------------------------------------------------------------------
# Step 5: END-state check — vainfo must report a working driver (FR-004).
# Failure names the GPU(s) + driver so the user knows exactly what broke.
# ---------------------------------------------------------------------------
_driver_label=""
[[ "${_has_intel}"  -eq 1 ]] && _driver_label="${_driver_label} intel-media-driver"
[[ "${_has_amd}"    -eq 1 ]] && _driver_label="${_driver_label} mesa-va-drivers-freeworld"
[[ "${_has_nvidia}" -eq 1 ]] && _driver_label="${_driver_label} libva-nvidia-driver"

if ! vainfo >/dev/null 2>&1; then
  die "va-hwaccel: vainfo reports no working VA-API driver after install (GPU:${_driver_label:-unknown} driver:${_driver_label:-unknown}) — check driver compatibility"
fi

log_ok "va-hwaccel: VA-API hardware acceleration configured"
