#!/usr/bin/env bash
# modules/rpmfusion/install.sh — enable RPM Fusion free + nonfree repos.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: install both RPM Fusion release packages via their upstream URLs.
# rpm -E %fedora expands to the running Fedora release number (e.g. "44").
# ---------------------------------------------------------------------------
fedora_rel="$(rpm -E %fedora)"
log_info "rpmfusion: enabling free + nonfree for Fedora ${fedora_rel}"

sudo dnf install -y \
  "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora_rel}.noarch.rpm" \
  "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora_rel}.noarch.rpm"

# ---------------------------------------------------------------------------
# Step 2: refresh repo metadata so new packages are immediately visible.
# ---------------------------------------------------------------------------
log_info "rpmfusion: refreshing repo metadata"
sudo dnf upgrade --refresh -y

# ---------------------------------------------------------------------------
# Step 3: install AppStream metadata for GUI software centres (GNOME Software,
# KDE Discover) so RPM Fusion packages appear with icons + descriptions.
# ---------------------------------------------------------------------------
log_info "rpmfusion: installing AppStream metadata"
sudo dnf install -y 'rpmfusion-*-appstream-data'

log_ok "rpmfusion: repositories enabled"
