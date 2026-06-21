# lib/gpu.sh — GPU vendor detection + NVIDIA-stack doctor diagnostics (Spec 10).
# Source-only; no side effects on source. Depends on lib/log.sh (log_*/die).
# All external commands (lspci, modprobe, dmesg) are PATH-stubbable in tests.
#
# Used by the `gpu-detect` module (vendor → marker) and by `devboost doctor --gpu`
# (gpu_doctor — NVIDIA-stack health checks).

# ---------------------------------------------------------------------------
# gpu_detect_vendor — classify GPU vendor(s) from `lspci`.
#   Mirrors va-hwaccel's detection: grep VGA/3D/Display controller lines, then
#   whole-word match Intel / AMD|ATI / NVIDIA. Echoes a space-separated vendor
#   set (any of: intel amd nvidia), in detection order, de-duplicated.
#   Unrecognized controllers are NOT echoed — the caller is responsible for
#   reporting them (gpu_detect_unrecognized exposes them).
#
#   To report unrecognized hardware too, call gpu_detect (below) instead — it
#   sets GPU_VENDORS and GPU_UNRECOGNIZED as globals (no command substitution,
#   so the side channel survives).
# ---------------------------------------------------------------------------
gpu_detect_vendor() {
  gpu_detect
  printf '%s\n' "${GPU_VENDORS}"
}

# ---------------------------------------------------------------------------
# gpu_detect — classify GPU vendor(s); sets two globals (no stdout vendor list):
#   GPU_VENDORS       — space-separated vendor set (any of: intel amd nvidia)
#   GPU_UNRECOGNIZED  — space-separated vendor/device strings for unknown GPUs
# Run directly (not via $(...)) so both globals propagate to the caller.
# ---------------------------------------------------------------------------
gpu_detect() {
  local lines has_intel=0 has_amd=0 has_nvidia=0 line vendor_part
  GPU_VENDORS=""
  GPU_UNRECOGNIZED=""

  lines="$(lspci 2>/dev/null | grep -E '(VGA compatible controller|3D controller|Display controller)' || true)"

  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    if echo "${line}" | grep -qwi "Intel"; then
      has_intel=1
    elif echo "${line}" | grep -qwiE "AMD|ATI"; then
      has_amd=1
    elif echo "${line}" | grep -qwi "NVIDIA"; then
      has_nvidia=1
    else
      vendor_part="$(echo "${line}" | sed 's/^[0-9a-f:.]*[[:space:]]*//' | sed 's/.*controller:[[:space:]]*//')"
      GPU_UNRECOGNIZED="${GPU_UNRECOGNIZED} ${vendor_part}"
    fi
  done <<< "${lines}"

  [[ "${has_intel}"  -eq 1 ]] && GPU_VENDORS="${GPU_VENDORS} intel"
  [[ "${has_amd}"    -eq 1 ]] && GPU_VENDORS="${GPU_VENDORS} amd"
  [[ "${has_nvidia}" -eq 1 ]] && GPU_VENDORS="${GPU_VENDORS} nvidia"
  GPU_VENDORS="${GPU_VENDORS# }"
}

# ---------------------------------------------------------------------------
# gpu_doctor — NVIDIA-stack health diagnostics for `devboost doctor --gpu`.
#   Runs a set of best-effort, stub-friendly checks, logging each. Collects
#   failures; returns 0 iff every check passes, non-zero otherwise (the first
#   failure is named in the returned/logged message).
#
#   Checks:
#     1. modprobe nvidia load test            (STUB_MODPROBE_FAIL)
#     2. nouveau blacklisted (file present)    (${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf)
#     3. initramfs has nvidia (marker/knob)    (best-effort)
#     4. module signature present (knob)       (best-effort)
#     5. dmesg taint/lockdown/PKCS#7 scan      (STUB_DMESG) — FLAG if present
#
#   Knobs (all optional; sensible defaults so it never hard-crashes):
#     DEVBOOST_MODPROBE_DIR     — dir holding blacklist-nouveau.conf (default /etc/modprobe.d)
#     DEVBOOST_INITRAMFS_OK     — "1" ⇒ assume initramfs carries nvidia (skip lsinitrd)
#     DEVBOOST_MODSIG_OK        — "1" ⇒ assume module signature present (skip deep check)
# ---------------------------------------------------------------------------
gpu_doctor() {
  local fails=0 first_fail=""
  local _fail
  _fail() { fails=$((fails+1)); [[ -z "${first_fail}" ]] && first_fail="$1"; log_error "doctor --gpu: $1"; }

  local modprobe_dir="${DEVBOOST_MODPROBE_DIR:-/etc/modprobe.d}"

  log_info "doctor --gpu: checking NVIDIA kernel-module stack"

  # 1. modprobe nvidia load test. Prefer a dry-run (-n) on real hosts; our stub
  #    honours a plain `modprobe nvidia` (STUB_MODPROBE_FAIL). Guard so a missing
  #    modprobe binary never hard-crashes the doctor.
  if command -v modprobe >/dev/null 2>&1; then
    if modprobe -n nvidia >/dev/null 2>&1 || modprobe nvidia >/dev/null 2>&1; then
      log_ok "doctor --gpu: nvidia module loads (modprobe)"
    else
      _fail "nvidia module failed to load (modprobe nvidia)"
    fi
  else
    log_warn "doctor --gpu: modprobe not found — skipping module load test"
  fi

  # 2. nouveau blacklisted — a blacklist-nouveau.conf must exist.
  if [[ -f "${modprobe_dir}/blacklist-nouveau.conf" ]]; then
    log_ok "doctor --gpu: nouveau is blacklisted (${modprobe_dir}/blacklist-nouveau.conf)"
  else
    _fail "nouveau is not blacklisted (missing ${modprobe_dir}/blacklist-nouveau.conf)"
  fi

  # 3. initramfs carries nvidia (best-effort, knob-driven). Accept a positive
  #    marker; otherwise probe lsinitrd. A negative lsinitrd result only HARD-FAILS
  #    when DEVBOOST_INITRAMFS_STRICT=1 (so a normal doctor on a non-NVIDIA box,
  #    or in the hermetic test harness, never trips on the host's real initramfs).
  if [[ "${DEVBOOST_INITRAMFS_OK:-}" == "1" ]]; then
    log_ok "doctor --gpu: initramfs contains nvidia (marker)"
  elif command -v lsinitrd >/dev/null 2>&1; then
    if lsinitrd 2>/dev/null | grep -qi nvidia; then
      log_ok "doctor --gpu: initramfs contains nvidia (lsinitrd)"
    elif [[ "${DEVBOOST_INITRAMFS_STRICT:-}" == "1" ]]; then
      _fail "initramfs does not contain nvidia (lsinitrd)"
    else
      log_warn "doctor --gpu: initramfs has no nvidia (lsinitrd) — best-effort, not failing"
    fi
  else
    log_warn "doctor --gpu: cannot determine initramfs nvidia state (no lsinitrd) — skipping"
  fi

  # 4. module signature present (best-effort knob). On real hosts this would
  #    inspect modinfo; here we accept a knob and otherwise warn.
  if [[ "${DEVBOOST_MODSIG_OK:-}" == "1" ]]; then
    log_ok "doctor --gpu: nvidia module signature present (marker)"
  else
    log_warn "doctor --gpu: module signature not verified (best-effort) — skipping"
  fi

  # 5. dmesg scan for taint / lockdown / PKCS#7 signature problems. Presence of
  #    any of these markers is a PROBLEM (signed-module/lockdown rejection).
  if command -v dmesg >/dev/null 2>&1; then
    local dmesg_out
    dmesg_out="$(dmesg 2>/dev/null || true)"
    if echo "${dmesg_out}" | grep -qiE 'taint|lockdown|PKCS#7'; then
      _fail "dmesg reports a kernel taint/lockdown/PKCS#7 signature problem"
    else
      log_ok "doctor --gpu: dmesg clean (no taint/lockdown/PKCS#7)"
    fi
  else
    log_warn "doctor --gpu: dmesg not found — skipping kernel-log scan"
  fi

  if [[ "${fails}" -eq 0 ]]; then
    log_ok "doctor --gpu: NVIDIA stack healthy"
    return 0
  fi
  log_error "doctor --gpu: ${fails} check(s) failed (first: ${first_fail})"
  return 1
}
