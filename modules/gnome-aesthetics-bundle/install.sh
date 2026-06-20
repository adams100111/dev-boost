#!/usr/bin/env bash
# modules/gnome-aesthetics-bundle/install.sh — OPT-IN aesthetics extensions.
# Install + enable the 5 aesthetics UUIDs via gext, author-verified, session-free, idempotent.
# Not in the default gnome profile — only activated via gnome-aesthetics profile.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/gnome.sh"

gnome_require

_AESTHETICS_UUIDS=(
  "blur-my-shell@aunetx"
  "just-perfection-desktop@just-perfection"
  "vertical-workspaces@G-dH.github.com"
  "monitor@astraext.github.io"
  "CoverflowAltTab@palatis.blogspot.com"
)

if [[ "${1:-}" == "--verify-only" ]]; then
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  for uuid in "${_AESTHETICS_UUIDS[@]}"; do
    ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
    if [[ ! -d "${ext_dir}" ]]; then
      log_error "gnome-aesthetics-bundle verify: extension dir absent for ${uuid}"
      exit 1
    fi
    if [[ "${enabled}" != *"${uuid}"* ]]; then
      log_error "gnome-aesthetics-bundle verify: ${uuid} not in enabled-extensions"
      exit 1
    fi
  done
  log_ok "gnome-aesthetics-bundle: all 5 aesthetics extensions present and enabled"
  exit 0
fi

# Ensure gext is available.
if ! have gext; then
  log_info "gnome-aesthetics-bundle: installing gext (gnome-extensions-cli)"
  pipx install gnome-extensions-cli --include-deps >/dev/null 2>&1 \
    || dnf_install python3-gnome-extensions-cli
fi

for uuid in "${_AESTHETICS_UUIDS[@]}"; do
  ext_install "${uuid}"
  if ! ext_verify_author "${uuid}"; then
    log_error "gnome-aesthetics-bundle: author-verify failed for ${uuid} — aborting"
    exit 1
  fi
  ext_enable "${uuid}"
done

log_ok "gnome-aesthetics-bundle: all 5 aesthetics extensions installed, verified, and enabled"
