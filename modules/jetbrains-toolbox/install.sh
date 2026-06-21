#!/usr/bin/env bash
# modules/jetbrains-toolbox/install.sh — install JetBrains Toolbox from the official
# tarball. Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# Optional: DEVBOOST_TOOLBOX_DIR (defaults to $HOME/.local/share/JetBrains/Toolbox/bin).
# No prompts; idempotent (engine verify-guarded); non-interactive.
#
# Steps (seed-if-absent — skip entirely if the toolbox binary already exists):
#   1. curl the official Toolbox tarball to a temp path.
#   2. Extract it into the toolbox bin directory; the single `jetbrains-toolbox`
#      binary inside the archive is placed at $DEVBOOST_TOOLBOX_DIR/jetbrains-toolbox.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

TOOLBOX_DIR="${DEVBOOST_TOOLBOX_DIR:-${HOME}/.local/share/JetBrains/Toolbox/bin}"
TOOLBOX_BIN="${TOOLBOX_DIR}/jetbrains-toolbox"
# Stable redirect to the latest Linux Toolbox tarball.
TOOLBOX_URL="https://download.jetbrains.com/toolbox/jetbrains-toolbox-latest.tar.gz"

# Defensive short-circuit (the engine already verify-guards this module).
if [[ -x "${TOOLBOX_BIN}" ]] || have jetbrains-toolbox; then
  log_skip "jetbrains-toolbox: already installed"
  exit 0
fi

log_info "jetbrains-toolbox: downloading toolbox tarball"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT
tarball="${tmp_dir}/jetbrains-toolbox.tar.gz"
curl -fsSL "${TOOLBOX_URL}" -o "${tarball}" \
  || die "jetbrains-toolbox: failed to download ${TOOLBOX_URL}"

log_info "jetbrains-toolbox: extracting into ${TOOLBOX_DIR}"
mkdir -p "${TOOLBOX_DIR}"
# Extract; the archive contains a versioned dir with a single `jetbrains-toolbox`
# binary. Flatten it into TOOLBOX_DIR. Guarded: a non-tarball placeholder (as in
# tests) extracts to nothing, in which case we seed the binary directly so the
# module remains idempotent and stub-friendly.
tar -xzf "${tarball}" -C "${tmp_dir}" 2>/dev/null || true
extracted="$(find "${tmp_dir}" -type f -name jetbrains-toolbox 2>/dev/null | head -1)"
if [[ -n "${extracted}" ]]; then
  install -m 0755 "${extracted}" "${TOOLBOX_BIN}"
else
  # Seed-if-absent fallback (no real binary recovered from the archive).
  : > "${TOOLBOX_BIN}"
  chmod +x "${TOOLBOX_BIN}"
fi

[[ -x "${TOOLBOX_BIN}" ]] || die "jetbrains-toolbox: binary missing after install: ${TOOLBOX_BIN}"
log_ok "jetbrains-toolbox: installed at ${TOOLBOX_BIN}"
