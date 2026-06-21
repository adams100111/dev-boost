#!/usr/bin/env bash
# modules/grub-btrfs/install.sh — install grub-btrfs, enable grub-btrfsd, regen menu.
# Sourced env: DEVBOOST_ROOT. No prompts; idempotent (verify-guarded).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: install grub-btrfs.
# ---------------------------------------------------------------------------
log_info "grub-btrfs: installing"
dnf_install grub-btrfs

# ---------------------------------------------------------------------------
# Step 2: enable the watcher daemon that regenerates entries on new snapshots.
# ---------------------------------------------------------------------------
log_info "grub-btrfs: enabling grub-btrfsd"
sudo systemctl enable grub-btrfsd

# ---------------------------------------------------------------------------
# Step 3: regenerate the GRUB menu so snapshot entries appear immediately.
# ---------------------------------------------------------------------------
log_info "grub-btrfs: regenerating GRUB menu"
sudo grub2-mkconfig -o /boot/grub2/grub.cfg

log_ok "grub-btrfs: ready"
