#!/usr/bin/env bash
# modules/secureboot-mok/verify.sh — GREEN iff Secure Boot is disabled OR the MOK is
# enrolled OR an enrollment is queued (i.e. not in the needs-import-and-undone state).
set -Eeuo pipefail

_CERT="${DEVBOOST_MOK_CERT:-/etc/pki/akmods/certs/public_key.der}"

_sb_state="$(mokutil --sb-state 2>/dev/null || true)"
[[ "${_sb_state}" != *enabled* ]] && exit 0          # SB off → nothing to enroll.

mokutil --test-key "${_CERT}" >/dev/null 2>&1 && exit 0   # already enrolled.
mokutil --list-new           >/dev/null 2>&1 && exit 0    # enrollment queued.

exit 1
