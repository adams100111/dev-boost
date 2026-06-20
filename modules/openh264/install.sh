#!/usr/bin/env bash
# modules/openh264/install.sh — enable Cisco OpenH264 repo + install browser H.264 components.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
# Verify (END state): rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264 all succeed.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: enable the Fedora Cisco OpenH264 repo (add-if-not-enabled; idempotent).
# ---------------------------------------------------------------------------
log_info "openh264: enabling fedora-cisco-openh264 repository"
sudo dnf config-manager setopt fedora-cisco-openh264.enabled=1

# ---------------------------------------------------------------------------
# Step 2: install the three OpenH264 components.
# ---------------------------------------------------------------------------
log_info "openh264: installing openh264 components"
sudo dnf install -y openh264 gstreamer1-plugin-openh264 mozilla-openh264

log_ok "openh264: browser H.264 support installed"
