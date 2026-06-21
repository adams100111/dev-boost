#!/usr/bin/env bash
# modules/nvidia-akmod/verify.sh — GREEN iff an nvidia kernel module is present for
# the running kernel (CRC32-converted). In tests, DEVBOOST_AKMOD_KO points at a fake
# .ko.xz whose <ko>.crc32 sentinel is written by install.sh.
set -Eeuo pipefail

_ko="${DEVBOOST_AKMOD_KO:-}"
if [[ -n "${_ko}" ]]; then
  [[ -e "${_ko}.crc32" ]] && exit 0
  exit 1
fi

# Production: an nvidia module (.ko or .ko.xz) exists under the running kernel.
find "/lib/modules/$(uname -r)" -name 'nvidia*.ko*' 2>/dev/null | grep -q . && exit 0
exit 1
