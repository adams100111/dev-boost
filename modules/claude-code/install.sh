#!/usr/bin/env bash
# modules/claude-code/install.sh — install Claude Code CLI via npm global.
# Sourced env: DEVBOOST_ROOT, HOME.
# No prompts; idempotent (safe to re-run). Never echoes tokens or secrets.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure a node runtime is available via mise ONLY when absent.
# If node is already on PATH (system package, nvm, etc.) we leave it alone.
# On a fresh machine with no node, we provision node@lts via mise so that
# npm is available for the global install below.
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  log_info "claude-code: no node found — provisioning node@lts via mise"
  mise use -g node@lts
  log_ok "claude-code: node@lts ensured via mise"
fi

# ---------------------------------------------------------------------------
# Step 2: install claude-code via npm global
# ---------------------------------------------------------------------------
log_info "claude-code: installing @anthropic-ai/claude-code via npm"
npm install -g @anthropic-ai/claude-code

log_ok "claude-code: installation complete"
