#!/usr/bin/env bash
# modules/restic-backup/install.sh — install restic + seed a sample user backup
# service/timer. NO secrets are committed: the units reference an env file the
# user provisions out-of-band (age-encrypted on the USB, per the mission).
# Sourced env: DEVBOOST_ROOT, HOME. Honors DEVBOOST_RESTIC_UNIT_DIR (tests).
# No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

unit_dir="${DEVBOOST_RESTIC_UNIT_DIR:-${HOME}/.config/systemd/user}"
conf_dir="${DEVBOOST_RESTIC_CONF_DIR:-${HOME}/.config/restic}"

# ---------------------------------------------------------------------------
# Step 1: install restic.
# ---------------------------------------------------------------------------
log_info "restic-backup: installing restic"
dnf_install restic

# ---------------------------------------------------------------------------
# Step 2: seed a sample repo config (NO secrets — env file is user-provisioned).
# ---------------------------------------------------------------------------
mkdir -p "${conf_dir}"
sample_conf="${conf_dir}/backup.env.sample"
if [[ ! -f "${sample_conf}" ]]; then
  log_info "restic-backup: seeding sample config ${sample_conf}"
  cat > "${sample_conf}" <<'CONF'
# dev-boost restic sample config — copy to backup.env and fill in.
# Provide secrets out-of-band (age-encrypted on the USB); never commit them.
#   RESTIC_REPOSITORY=...        # e.g. sftp:user@host:/srv/restic or rest:https://...
#   RESTIC_PASSWORD_FILE=...     # path to a file holding the repo password
# Paths to back up (space-separated):
#   RESTIC_BACKUP_PATHS="$HOME/Documents $HOME/Projects"
CONF
fi

# ---------------------------------------------------------------------------
# Step 3: seed the service + timer unit files (idempotent: overwrite-if-managed).
# ---------------------------------------------------------------------------
mkdir -p "${unit_dir}"
log_info "restic-backup: seeding service + timer in ${unit_dir}"
cat > "${unit_dir}/restic-backup.service" <<CONF
[Unit]
Description=dev-boost restic backup (sample)
Documentation=https://restic.readthedocs.io

[Service]
Type=oneshot
EnvironmentFile=-${conf_dir}/backup.env
ExecStart=/usr/bin/restic backup \$RESTIC_BACKUP_PATHS
CONF

cat > "${unit_dir}/restic-backup.timer" <<'CONF'
[Unit]
Description=Run dev-boost restic backup daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
CONF

# ---------------------------------------------------------------------------
# Step 4: enable the (user) timer.
# ---------------------------------------------------------------------------
log_info "restic-backup: enabling restic-backup.timer"
systemctl --user enable restic-backup.timer

log_ok "restic-backup: ready"
