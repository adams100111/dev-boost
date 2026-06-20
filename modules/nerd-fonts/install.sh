#!/usr/bin/env bash
# modules/nerd-fonts/install.sh — install JetBrainsMono and MesloLGS Nerd Fonts.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (font presence check + fc-cache); non-interactive.
#
# Pinned font release: Nerd Fonts v3.2.1 (2024-04-06)
# URLs resolved from: https://github.com/ryanoasis/nerd-fonts/releases/tag/v3.2.1
#
# Ptyxis / GNOME Terminal font gotcha:
#   Ptyxis (and classic GNOME Terminal) require a font whose family name ends in
#   "Mono" for the monospace selector to show it.  Use "JetBrainsMono Nerd Font Mono"
#   or "MesloLGS NF" — NOT "JetBrainsMono Nerd Font" (which is proportional-weight).
#   In Ghostty, use font-family = "JetBrainsMono Nerd Font Mono" (the Mono variant
#   is the fixed-width face and is the correct choice for a terminal emulator).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Pinned download base URL (Nerd Fonts v3.2.1)
# ---------------------------------------------------------------------------
readonly _NF_VERSION="v3.2.1"
readonly _NF_BASE="https://github.com/ryanoasis/nerd-fonts/releases/download/${_NF_VERSION}"

# ---------------------------------------------------------------------------
# Font destination directory (user-local; no sudo required)
# ---------------------------------------------------------------------------
readonly _FONT_DIR="${HOME}/.local/share/fonts"

# ---------------------------------------------------------------------------
# Ensure unzip is available (required to extract font archives).
# ---------------------------------------------------------------------------
need_cmd unzip unzip

# ---------------------------------------------------------------------------
# Step 1: check whether JetBrainsMono Nerd Font is already installed.
# If fc-list already reports it, skip the download step entirely.
# ---------------------------------------------------------------------------
if fc-list | grep -qi 'JetBrainsMono Nerd Font'; then
  log_skip "nerd-fonts: JetBrainsMono Nerd Font already present — skipping download"
else
  log_info "nerd-fonts: creating font directory ${_FONT_DIR}"
  mkdir -p "${_FONT_DIR}"

  # Create a temp directory for zip archives; cleaned up on exit.
  _nf_tmp="$(mktemp -d)"
  trap 'rm -rf "${_nf_tmp}"' EXIT

  # -------------------------------------------------------------------------
  # Step 2a: download JetBrainsMono Nerd Font archive (pinned) and extract
  # the .ttf files directly into the font directory.
  # -------------------------------------------------------------------------
  log_info "nerd-fonts: downloading JetBrainsMono Nerd Font ${_NF_VERSION}"
  curl -fsSL \
    -o "${_nf_tmp}/JetBrainsMono.zip" \
    "${_NF_BASE}/JetBrainsMono.zip" \
    || { log_error "nerd-fonts: failed to download JetBrainsMono"; exit 1; }

  log_info "nerd-fonts: extracting JetBrainsMono .ttf files"
  unzip -o -j "${_nf_tmp}/JetBrainsMono.zip" '*.ttf' -d "${_FONT_DIR}" \
    || { log_error "nerd-fonts: failed to extract JetBrainsMono"; exit 1; }

  # -------------------------------------------------------------------------
  # Step 2b: download MesloLGS Nerd Font Mono archive (pinned) and extract.
  # MesloLGS is the recommended font for Powerlevel10k and widely used with
  # Starship.  Its name ends in "NF" so Ptyxis recognises it as monospace.
  # -------------------------------------------------------------------------
  log_info "nerd-fonts: downloading MesloLGS Nerd Font Mono ${_NF_VERSION}"
  curl -fsSL \
    -o "${_nf_tmp}/Meslo.zip" \
    "${_NF_BASE}/Meslo.zip" \
    || { log_error "nerd-fonts: failed to download MesloLGS"; exit 1; }

  log_info "nerd-fonts: extracting MesloLGS .ttf files"
  unzip -o -j "${_nf_tmp}/Meslo.zip" '*.ttf' -d "${_FONT_DIR}" \
    || { log_error "nerd-fonts: failed to extract MesloLGS"; exit 1; }
fi

# ---------------------------------------------------------------------------
# Step 3: rebuild the fontconfig cache so the fonts are immediately usable.
# Always run fc-cache even when fonts were skipped to ensure the cache is
# consistent with the current font directory state.
# ---------------------------------------------------------------------------
log_info "nerd-fonts: rebuilding fontconfig cache"
fc-cache -f

log_ok "nerd-fonts: JetBrainsMono + MesloLGS Nerd Fonts installed"
