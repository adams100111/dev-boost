#!/usr/bin/env bash
# modules/claude-code/install.sh — install Claude Code CLI via npm global.
# Sourced env: DEVBOOST_ROOT, HOME.
# No prompts; idempotent (safe to re-run). Never echoes tokens or secrets.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

# ---------------------------------------------------------------------------
# Step 1 (F2): ensure a node runtime is available via mise FIRST.
# On a fresh machine's mise, node may not be provisioned yet and npm would be
# missing.  Always run `mise use -g node@lts` to ensure node is managed and
# current before attempting any npm global install.
# ---------------------------------------------------------------------------
log_info "claude-code: ensuring node@lts is available via mise"
mise use -g node@lts
log_ok "claude-code: node@lts ensured via mise"

# ---------------------------------------------------------------------------
# Step 2: install claude-code via npm global
# ---------------------------------------------------------------------------
log_info "claude-code: installing @anthropic-ai/claude-code via npm"
npm install -g @anthropic-ai/claude-code

log_ok "claude-code: installation complete"
