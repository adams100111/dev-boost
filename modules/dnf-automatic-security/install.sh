#!/usr/bin/env bash
# modules/dnf-automatic-security/install.sh — install dnf-automatic, configure it
# for security-only upgrades, and enable the timer.
# Sourced env: DEVBOOST_ROOT. Honors DEVBOOST_DNF_AUTOMATIC_CONF override (tests).
# No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

conf="${DEVBOOST_DNF_AUTOMATIC_CONF:-/etc/dnf/automatic.conf}"

# ---------------------------------------------------------------------------
# Step 1: install dnf-automatic.
# ---------------------------------------------------------------------------
log_info "dnf-automatic-security: installing dnf-automatic"
dnf_install dnf-automatic

# ---------------------------------------------------------------------------
# Step 2: write a security-only automatic.conf (idempotent: skip if already set).
# upgrade_type = security ensures ONLY security errata are applied unattended.
# ---------------------------------------------------------------------------
if grep -q '^upgrade_type = security$' "${conf}" 2>/dev/null; then
  log_skip "dnf-automatic-security: ${conf} already security-only"
else
  log_info "dnf-automatic-security: writing security-only config to ${conf}"
  mkdir -p "$(dirname "${conf}")"
  cat > "${conf}" <<'CONF'
# Managed by dev-boost — security-only unattended updates.
[commands]
upgrade_type = security
random_sleep = 0
download_updates = yes
apply_updates = yes

[emitters]
emit_via = stdio

[base]
debuglevel = 1
CONF
fi

# ---------------------------------------------------------------------------
# Step 3: enable the timer.
# ---------------------------------------------------------------------------
log_info "dnf-automatic-security: enabling dnf-automatic.timer"
sudo systemctl enable dnf-automatic.timer

log_ok "dnf-automatic-security: ready"
