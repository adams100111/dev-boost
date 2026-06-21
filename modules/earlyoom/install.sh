#!/usr/bin/env bash
# modules/earlyoom/install.sh — install earlyoom + tune its OOM kill policy:
#   --avoid critical dev daemons; --prefer memory-hungry GUI apps.
# Sourced env: DEVBOOST_ROOT. Honors DEVBOOST_EARLYOOM_CONF override (tests).
# No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

conf="${DEVBOOST_EARLYOOM_CONF:-/etc/default/earlyoom}"

# ---------------------------------------------------------------------------
# Step 1: install earlyoom.
# ---------------------------------------------------------------------------
log_info "earlyoom: installing"
dnf_install earlyoom

# ---------------------------------------------------------------------------
# Step 2: write the tuned EARLYOOM_ARGS (idempotent: skip if already tuned).
#   --avoid : never kill these (build/dev/session-critical) processes.
#   --prefer: kill these (browsers/electron chat apps) first when low on memory.
# ---------------------------------------------------------------------------
avoid='(^|/)(dockerd|dotnet|dcp|sshd|code|gnome-shell)$'
prefer='(^|/)(firefox|chrome|chromium|electron|QtWebEngine|brave|slack|discord)$'

if grep -q -- '--avoid' "${conf}" 2>/dev/null && grep -q -- '--prefer' "${conf}" 2>/dev/null; then
  log_skip "earlyoom: ${conf} already tuned"
else
  log_info "earlyoom: writing tuned policy to ${conf}"
  mkdir -p "$(dirname "${conf}")"
  cat > "${conf}" <<CONF
# Managed by dev-boost — protect dev daemons, sacrifice memory-hungry GUI apps.
EARLYOOM_ARGS="-r 3600 --avoid '${avoid}' --prefer '${prefer}'"
CONF
fi

# ---------------------------------------------------------------------------
# Step 3: enable the earlyoom service.
# ---------------------------------------------------------------------------
log_info "earlyoom: enabling service"
sudo systemctl enable earlyoom

log_ok "earlyoom: ready"
