#!/usr/bin/env bash
# modules/secureboot-mok/install.sh — Secure Boot MOK enrollment (Spec 10, FR-008).
# Fedora-only; idempotent (verify-guarded); the only possibly-interactive moment is the
# one-time firmware MOK enrollment screen on the NEXT reboot (not at install time).
#
# State machine (mokutil):
#   sb-state disabled        → nothing to enroll; skip + exit 0.
#   enabled + enrolled       → key already trusted; no-op.
#   enabled + queued (--list-new) → enrollment pending; tell the user to reboot.
#   enabled + neither        → generate CA if absent, then `mokutil --import` (queues it).
#
# Test override: DEVBOOST_MOK_CERT (default /etc/pki/akmods/certs/public_key.der).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

_CERT="${DEVBOOST_MOK_CERT:-/etc/pki/akmods/certs/public_key.der}"

_sb_state="$(mokutil --sb-state 2>/dev/null || true)"

if [[ "${_sb_state}" != *enabled* ]]; then
  log_skip "secureboot-mok: Secure Boot disabled — no MOK enrollment needed"
  exit 0
fi

if mokutil --test-key "${_CERT}" >/dev/null 2>&1; then
  log_ok "secureboot-mok: MOK already enrolled"
  exit 0
fi

if mokutil --list-new >/dev/null 2>&1; then
  log_warn "secureboot-mok: MOK enrollment queued — reboot to finish enrollment (firmware MOK screen)"
  exit 0
fi

# Needs import: generate the akmods CA only if absent, then queue the import.
if [[ ! -e "${_CERT}" ]]; then
  log_info "secureboot-mok: generating akmods signing CA (kmodgenca -a)"
  sudo kmodgenca -a
else
  log_skip "secureboot-mok: signing CA already present (${_CERT})"
fi

log_info "secureboot-mok: importing MOK (mokutil --import ${_CERT})"
sudo mokutil --import "${_CERT}"
log_warn "secureboot-mok: MOK import queued — reboot and complete the firmware MOK enrollment screen"
