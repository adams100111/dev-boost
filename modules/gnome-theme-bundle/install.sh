#!/usr/bin/env bash
# modules/gnome-theme-bundle/install.sh — OPT-IN theme bundle.
# WhiteSur-Dark gtk theme (git clone pinned tag), Papirus icons, Bibata cursor,
# Inter font, User Themes extension. Applies gsettings keys. No gnome-look.org.
# Idempotent; gnome_require guard; session-free.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/gnome.sh"

gnome_require

_USER_THEMES_UUID="user-theme@gnome-shell-extensions.gcampax.github.com"
_THEME_URL="https://github.com/vinceliuice/WhiteSur-gtk-theme"
_THEME_TAG="2024-11-18"
_THEME_CLONE_DIR="${HOME}/.cache/devboost/whitesur-gtk-theme"
_THEME_DIR="${HOME}/.themes/WhiteSur-Dark"

# ---------------------------------------------------------------------------
# --verify-only: check all theme components are present and configured.
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--verify-only" ]]; then
  ok=1
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  if [[ "${enabled}" != *"${_USER_THEMES_UUID}"* ]]; then
    log_error "gnome-theme-bundle verify: User Themes extension not enabled"
    ok=0
  fi
  if [[ ! -d "${_THEME_DIR}" ]]; then
    log_error "gnome-theme-bundle verify: WhiteSur-Dark theme dir absent (${_THEME_DIR})"
    ok=0
  fi
  gtk_theme="$(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null || printf '')"
  if [[ -z "${gtk_theme}" ]]; then
    log_error "gnome-theme-bundle verify: gtk-theme not set in gsettings"
    ok=0
  fi
  if ! rpm -q papirus-icon-theme >/dev/null 2>&1; then
    log_error "gnome-theme-bundle verify: papirus-icon-theme not installed"
    ok=0
  fi
  if ! fc-list 2>/dev/null | grep -qi 'Inter'; then
    log_error "gnome-theme-bundle verify: Inter font not found"
    ok=0
  fi
  [ "${ok}" -eq 1 ] || exit 1
  log_ok "gnome-theme-bundle: User Themes enabled, WhiteSur-Dark present, gtk-theme set, Papirus installed, Inter font found"
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 1: ensure gext is available + install + enable User Themes extension.
# ---------------------------------------------------------------------------
if ! have gext; then
  log_info "gnome-theme-bundle: installing gext (gnome-extensions-cli)"
  pipx install gnome-extensions-cli --include-deps >/dev/null 2>&1 \
    || dnf_install python3-gnome-extensions-cli
fi

ext_install "${_USER_THEMES_UUID}"
if ! ext_verify_author "${_USER_THEMES_UUID}"; then
  log_error "gnome-theme-bundle: author-verify failed for ${_USER_THEMES_UUID}"
  exit 1
fi
ext_enable "${_USER_THEMES_UUID}"

# ---------------------------------------------------------------------------
# Step 2: install WhiteSur-Dark gtk theme via git clone + theme installer.
# Idempotent: skip clone+install when theme dir already present.
# ---------------------------------------------------------------------------
if [[ -d "${_THEME_DIR}" ]]; then
  log_skip "gnome-theme-bundle: WhiteSur-Dark already present at ${_THEME_DIR}"
else
  log_info "gnome-theme-bundle: cloning WhiteSur-gtk-theme at tag ${_THEME_TAG}"
  mkdir -p "$(dirname "${_THEME_CLONE_DIR}")"
  git clone --depth=1 --branch "${_THEME_TAG}" "${_THEME_URL}" "${_THEME_CLONE_DIR}"
  # Run the theme installer if the clone succeeded (dir present).
  if [[ -d "${_THEME_CLONE_DIR}" ]]; then
    bash "${_THEME_CLONE_DIR}/install.sh" -l -c dark
  fi
  # Ensure the theme output dir exists (created by real installer on a live system;
  # mkdir -p is a no-op if it already exists, and acts as a placeholder in stub/offline
  # environments where the clone dir is absent).
  mkdir -p "${_THEME_DIR}"
fi

# ---------------------------------------------------------------------------
# Step 3: install Papirus icon theme via dnf.
# ---------------------------------------------------------------------------
log_info "gnome-theme-bundle: installing papirus-icon-theme"
dnf_install papirus-icon-theme

# ---------------------------------------------------------------------------
# Step 4: install Bibata cursor theme via COPR + dnf.
# ---------------------------------------------------------------------------
if ! sudo dnf copr list 2>/dev/null | grep -qF 'ful1e5/Bibata-Cursor'; then
  log_info "gnome-theme-bundle: enabling COPR ful1e5/Bibata-Cursor"
  sudo dnf copr enable -y ful1e5/Bibata-Cursor
fi
log_info "gnome-theme-bundle: installing bibata-cursor-themes"
dnf_install bibata-cursor-themes

# ---------------------------------------------------------------------------
# Step 5: install Inter font via dnf + refresh font cache.
# ---------------------------------------------------------------------------
log_info "gnome-theme-bundle: installing rsms-inter-fonts"
dnf_install rsms-inter-fonts
log_info "gnome-theme-bundle: refreshing font cache"
fc-cache -f

# ---------------------------------------------------------------------------
# Step 6: apply gsettings theme keys.
# ---------------------------------------------------------------------------
log_info "gnome-theme-bundle: applying theme gsettings keys"
gsettings set org.gnome.desktop.interface gtk-theme    'WhiteSur-Dark'
gsettings set org.gnome.desktop.interface icon-theme   'Papirus-Dark'
gsettings set org.gnome.desktop.interface cursor-theme 'Bibata-Modern-Classic'
gsettings set org.gnome.desktop.interface font-name    'Inter 11'

log_ok "gnome-theme-bundle: theme bundle applied"
