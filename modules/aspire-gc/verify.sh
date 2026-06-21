#!/usr/bin/env bash
# modules/aspire-gc/verify.sh — GREEN iff both user units are present. Read-only.
set -Eeuo pipefail
ud="${HOME}/.config/systemd/user"
[[ -f "${ud}/aspire-gc.service" && -f "${ud}/aspire-gc.timer" ]] || exit 1
exit 0
