#!/usr/bin/env bash
# modules/neovim/install.sh — install Neovim and bootstrap the LazyVim starter.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# Optional: XDG_CONFIG_HOME (defaults to $HOME/.config).
# No prompts; idempotent (engine verify-guarded); non-interactive.
#
# Steps:
#   1. dnf install neovim.
#   2. Seed-if-absent: clone the LazyVim starter into $XDG_CONFIG_HOME/nvim only
#      when that directory does not already exist (never clobber an existing config).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

LAZYVIM_STARTER="https://github.com/LazyVim/starter"
NVIM_CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nvim"

# --- Step 1: install Neovim ---------------------------------------------------
log_info "neovim: installing neovim"
dnf_install neovim

# --- Step 2: bootstrap LazyVim (seed-if-absent) -------------------------------
if [[ -d "${NVIM_CONFIG_DIR}" ]]; then
  log_skip "neovim: ${NVIM_CONFIG_DIR} already present — leaving config untouched"
else
  log_info "neovim: bootstrapping LazyVim starter into ${NVIM_CONFIG_DIR}"
  mkdir -p "$(dirname "${NVIM_CONFIG_DIR}")"
  git clone "${LAZYVIM_STARTER}" "${NVIM_CONFIG_DIR}" \
    || die "neovim: failed to clone LazyVim starter from ${LAZYVIM_STARTER}"
  # Drop the starter's git history so the user's nvim config is their own.
  rm -rf "${NVIM_CONFIG_DIR}/.git"
fi

log_ok "neovim: installed with LazyVim starter config"
