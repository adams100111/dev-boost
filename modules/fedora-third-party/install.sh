#!/usr/bin/env bash
# modules/fedora-third-party/install.sh — enable Fedora third-party repos.
# Sourced env: DEVBOOST_ROOT.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "fedora-third-party: enabling third-party repository support"
sudo fedora-third-party enable

log_ok "fedora-third-party: third-party repos enabled"
