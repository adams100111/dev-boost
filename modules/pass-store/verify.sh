#!/usr/bin/env bash
# modules/pass-store/verify.sh — GREEN iff the pass store is initialized. Read-only.
set -Eeuo pipefail
store="${PASSWORD_STORE_DIR:-${HOME}/.password-store}"
[[ -f "${store}/.gpg-id" ]] || exit 1
exit 0
