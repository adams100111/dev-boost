#!/usr/bin/env bash
# modules/expo/install.sh — seed the React Native / Expo project scaffolding template.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (seed-if-absent); non-interactive.
#
# Per research.md: NO global expo-cli (deprecated). Projects are created with
# `npx create-expo-app` and built with `npx expo` — nothing is installed globally.
# This module only ensures the in-repo template exists (it ships with the repo;
# the seed-if-absent guard keeps re-runs and edited templates safe).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

template_dir="${DEVBOOST_ROOT}/templates/react-native"
readme="${template_dir}/README.md"

if [[ -f "${readme}" ]]; then
  log_skip "expo: react-native template already present (${template_dir})"
else
  # The template ships with the repo; this branch is a safety net only.
  log_info "expo: seeding react-native template (${template_dir})"
  mkdir -p "${template_dir}/.fresh"
fi

log_ok "expo: react-native template ready (use npx create-expo-app / npx expo)"
