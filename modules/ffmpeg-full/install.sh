#!/usr/bin/env bash
# modules/ffmpeg-full/install.sh — replace ffmpeg-free with the full RPM Fusion ffmpeg build.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive.
# Verify (END state): ffmpeg present AND ffmpeg-free absent — so a re-run is a clean skip.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

log_info "ffmpeg-full: swapping ffmpeg-free for full ffmpeg"
sudo dnf swap ffmpeg-free ffmpeg --allowerasing -y

log_ok "ffmpeg-full: full ffmpeg installed"
