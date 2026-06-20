#!/usr/bin/env bash
# modules/dnf-tune/install.sh — tune /etc/dnf/dnf.conf for faster bootstraps.
# Sourced env: DEVBOOST_ROOT, DEVBOOST_DNF_CONF (optional, defaults to /etc/dnf/dnf.conf).
# No prompts; idempotent (write_kv_conf reconciles-not-duplicates); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# Allow tests to override the dnf.conf path so no root access is required.
DNF_CONF="${DEVBOOST_DNF_CONF:-/etc/dnf/dnf.conf}"

log_info "dnf-tune: configuring ${DNF_CONF}"

# Reconcile (not duplicate) each key=value pair.
write_kv_conf "${DNF_CONF}" max_parallel_downloads 10
write_kv_conf "${DNF_CONF}" fastestmirror true

log_ok "dnf-tune: dnf.conf tuned (max_parallel_downloads=10, fastestmirror=true)"
