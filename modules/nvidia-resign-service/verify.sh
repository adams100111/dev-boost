#!/usr/bin/env bash
# modules/nvidia-resign-service/verify.sh — GREEN iff the signing helper + the oneshot
# unit are present (enablement is best-effort, not asserted here).
set -Eeuo pipefail

_SBIN_DIR="${DEVBOOST_SBIN_DIR:-/usr/local/sbin}"
_UNIT_DIR="${DEVBOOST_SYSTEMD_SYSTEM_DIR:-/etc/systemd/system}"

[[ -f "${_SBIN_DIR}/sign-nvidia-modules" ]] || exit 1
[[ -f "${_UNIT_DIR}/nvidia-resign.service" ]] || exit 1
exit 0
