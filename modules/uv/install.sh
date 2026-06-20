#!/usr/bin/env bash
# modules/uv/install.sh — install uv (Python package/project manager) via the pinned astral installer.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (skip if uv already present); non-interactive.
#
# Pin (in-repo source of truth, Principle III; context7-verified 2026-06): uv 0.11.23.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if have uv; then
  log_skip "uv: already installed — skipping"
  exit 0
fi

log_info "uv: installing via pinned astral installer (0.11.23)"
curl -LsSf https://astral.sh/uv/0.11.23/install.sh | sh

log_ok "uv: installed"
