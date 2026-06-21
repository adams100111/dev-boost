#!/usr/bin/env bash
# modules/snapper/install.sh — install snapper + create a 'root' snapshot config.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 0: snapshots require a Btrfs root. Detect the fstype of "/" and die
# clearly if it is not btrfs (stub-friendly: findmnt is stubbed in tests).
# ---------------------------------------------------------------------------
root_fs="$(findmnt -no FSTYPE / 2>/dev/null || true)"
if [[ "${root_fs}" != "btrfs" ]]; then
  die "snapper: root filesystem is '${root_fs:-unknown}', not Btrfs — snapshots unsupported"
fi

# ---------------------------------------------------------------------------
# Step 1: install snapper.
# ---------------------------------------------------------------------------
log_info "snapper: installing"
dnf_install snapper

# ---------------------------------------------------------------------------
# Step 2: create the 'root' config for / only if it does not already exist.
# ---------------------------------------------------------------------------
if snapper list-configs 2>/dev/null | grep -qw root; then
  log_skip "snapper: 'root' config already present"
else
  log_info "snapper: creating 'root' config for /"
  sudo snapper -c root create-config /
fi

log_ok "snapper: ready"
