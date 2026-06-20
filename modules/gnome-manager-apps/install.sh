#!/usr/bin/env bash
# modules/gnome-manager-apps/install.sh — install GNOME management toolchain.
# Extensions app (gnome-extensions-app dnf), Extension Manager (flatpak), gnome-tweaks.
# Idempotent; add-if-absent for flatpak remote + Extension Manager.
# No secrets. No prompts. Non-interactive.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/gnome.sh"

gnome_require

# --verify-only: check all three apps are present.
if [[ "${1:-}" == "--verify-only" ]]; then
  ok=1
  if ! command -v gnome-tweaks >/dev/null 2>&1; then
    log_error "gnome-manager-apps verify: gnome-tweaks not found"
    ok=0
  fi
  if ! flatpak list 2>/dev/null | grep -q 'com.mattjakeman.ExtensionManager'; then
    log_error "gnome-manager-apps verify: Extension Manager flatpak not present"
    ok=0
  fi
  if ! command -v gnome-extensions >/dev/null 2>&1 && \
     ! flatpak list 2>/dev/null | grep -q 'org.gnome.Extensions'; then
    log_error "gnome-manager-apps verify: GNOME Extensions app not found (neither gnome-extensions nor org.gnome.Extensions flatpak)"
    ok=0
  fi
  [ "${ok}" -eq 1 ] || exit 1
  log_ok "gnome-manager-apps: all manager apps present"
  exit 0
fi

# Step 1: install GNOME Extensions app (official) via dnf.
log_info "gnome-manager-apps: installing gnome-extensions-app"
dnf_install gnome-extensions-app

# Step 2: add Flathub remote (add-if-absent).
flatpak_remote_add flathub "https://flathub.org/repo/flathub.flatpakrepo"

# Step 3: install Extension Manager flatpak (add-if-absent).
if flatpak list 2>/dev/null | grep -q 'com.mattjakeman.ExtensionManager'; then
  log_skip "gnome-manager-apps: Extension Manager already installed"
else
  log_info "gnome-manager-apps: installing Extension Manager (flatpak)"
  flatpak install -y flathub com.mattjakeman.ExtensionManager
fi

# Step 4: install gnome-tweaks via dnf.
log_info "gnome-manager-apps: installing gnome-tweaks"
dnf_install gnome-tweaks

log_ok "gnome-manager-apps: manager toolchain installed"
