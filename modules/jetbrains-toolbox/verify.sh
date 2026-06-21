#!/usr/bin/env bash
# modules/jetbrains-toolbox/verify.sh — idempotency guard for the jetbrains-toolbox module.
# GREEN iff the Toolbox binary is present at the expected path (honouring the
# DEVBOOST_TOOLBOX_DIR override) OR `jetbrains-toolbox` is on PATH. Read-only.
set -Eeuo pipefail

TOOLBOX_DIR="${DEVBOOST_TOOLBOX_DIR:-${HOME}/.local/share/JetBrains/Toolbox/bin}"
[[ -x "${TOOLBOX_DIR}/jetbrains-toolbox" ]] && exit 0
command -v jetbrains-toolbox >/dev/null 2>&1 && exit 0
exit 1
