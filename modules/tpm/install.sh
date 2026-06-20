#!/usr/bin/env bash
# modules/tpm/install.sh — install tmux plugin manager via git clone.
# Sourced env: DEVBOOST_ROOT, HOME.
# No prompts; idempotent (safe to re-run).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

_tpm_dir="${HOME}/.tmux/plugins/tpm"

# ---------------------------------------------------------------------------
# Idempotency guard: skip if tpm directory already exists
# ---------------------------------------------------------------------------
if [[ -d "${_tpm_dir}" ]]; then
  log_skip "tpm: already present at ${_tpm_dir}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Clone tpm from GitHub
# ---------------------------------------------------------------------------
log_info "tpm: cloning tmux plugin manager"
mkdir -p "${HOME}/.tmux/plugins"
git clone https://github.com/tmux-plugins/tpm "${_tpm_dir}"

log_ok "tpm: installed at ${_tpm_dir}"
