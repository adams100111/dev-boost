#!/usr/bin/env bash
# modules/codecs/install.sh — install the @multimedia codec group from RPM Fusion.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
# Verify (END state): representative @multimedia member gstreamer1-plugins-bad-freeworld present.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "codecs: installing @multimedia codec group"
sudo dnf update @multimedia --setopt="install_weak_deps=False" \
  --exclude=PackageKit-gstreamer-plugin -y

log_ok "codecs: @multimedia codec group installed"
