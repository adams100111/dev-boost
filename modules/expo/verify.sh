#!/usr/bin/env bash
# modules/expo/verify.sh — idempotency guard for the expo module.
# GREEN iff the react-native template README is present. No prompts; read-only.
set -Eeuo pipefail

[[ -f "${DEVBOOST_ROOT}/templates/react-native/README.md" ]] || exit 1

exit 0
