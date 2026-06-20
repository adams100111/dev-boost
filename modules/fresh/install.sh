#!/usr/bin/env bash
# modules/fresh/install.sh — install the sinelaw/fresh terminal editor.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (engine verify-guarded); non-interactive.
#
# Install channels, tried in order, stopping at the first that puts `fresh` on PATH:
#   1. Fedora .rpm from the latest GitHub release (sudo rpm -U).
#   2. Official autodetect install script (curl … | sh).
#   3. Fallback: cargo install --locked fresh-editor (cargo from base build-tools/mise).
# If all three fail, the module fails NAMING the editor + the last command (never silent).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

REPO="sinelaw/fresh"
API="https://api.github.com/repos/${REPO}/releases/latest"
INSTALL_SH="https://raw.githubusercontent.com/${REPO}/refs/heads/master/scripts/install.sh"

# Defensive short-circuit (the engine already verify-guards this module).
if have fresh; then
  log_skip "fresh: already installed"
  exit 0
fi

# --- Channel 1: Fedora .rpm from the latest GitHub release --------------------
_install_via_rpm() {
  local arch url rpm
  arch="$(uname -m)"
  log_info "fresh: resolving latest .rpm release asset"
  url="$(curl -fsSL "${API}" 2>/dev/null \
        | grep -oE '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*'"${arch}"'\.rpm"' \
        | head -1 | sed -E 's/.*"(https[^"]*)"$/\1/')" || return 1
  [[ -n "${url}" ]] || return 1
  rpm="$(mktemp -d)/fresh-editor.rpm"
  curl -fsSL "${url}" -o "${rpm}" || return 1
  sudo rpm -U "${rpm}" || return 1
}

# --- Channel 2: official autodetect install script ----------------------------
_install_via_script() {
  curl -fsSL "${INSTALL_SH}" | sh
}

# --- Channel 3: cargo fallback ------------------------------------------------
_install_via_cargo() {
  cargo install --locked fresh-editor
}

last=""
for channel in rpm script cargo; do
  case "${channel}" in
    rpm)    log_info "fresh: trying Fedora .rpm release";        _install_via_rpm    || true; last="rpm release install" ;;
    script) log_info "fresh: trying official install script";    _install_via_script || true; last="official install script" ;;
    cargo)  log_info "fresh: trying cargo install --locked";     _install_via_cargo  || true; last="cargo install --locked fresh-editor" ;;
  esac
  if have fresh; then
    log_ok "fresh: installed via ${channel}"
    exit 0
  fi
done

die "fresh: install failed — rpm release, official script, and cargo all failed (last: ${last})"
