#!/usr/bin/env bash
# modules/aspire-gc/install.sh — install an hourly `devboost dev gc` systemd --user timer.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME, XDG_*.
# No prompts; idempotent (overwrite-in-place + enable no-op); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

ud="${HOME}/.config/systemd/user"
logf="${XDG_STATE_HOME:-${HOME}/.local/state}/devboost/aspire-gc.log"
mkdir -p "${ud}"

cat > "${ud}/aspire-gc.service" <<UNIT
[Unit]
Description=devboost Aspire/dev-container GC (devboost dev gc)

[Service]
Type=oneshot
ExecStart=/bin/bash -lc 'mkdir -p "$(dirname "${logf}")"; "${DEVBOOST_ROOT}/bin/devboost" dev gc >> "${logf}" 2>&1'
UNIT

cat > "${ud}/aspire-gc.timer" <<'UNIT'
[Unit]
Description=devboost hourly Aspire/dev-container GC

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
UNIT

# Run without an active session (headless); tolerate stub/no-systemd.
loginctl enable-linger "$(id -un)" 2>/dev/null || true
systemctl --user enable --now aspire-gc.timer 2>/dev/null || true

log_ok "aspire-gc: hourly dev-gc timer installed and enabled"
