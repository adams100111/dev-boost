#!/usr/bin/env bash
# modules/android-sdk/install.sh — provision the Android SDK for React Native.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (skip the whole SDK provisioning when already accepted);
# non-interactive (licenses auto-accepted via `yes | sdkmanager --licenses`).
#
# Pins (in-repo source of truth, Principle III; context7-verified 2026-06):
#   JDK temurin-17 (RN's validated chain), Android API 35, build-tools 36.0.0.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# Pinned Android command-line tools (Linux) archive — in-repo source of truth.
CMDLINE_TOOLS_VERSION="13114758"
CMDLINE_TOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_VERSION}_latest.zip"

# RN's validated JDK — provisioned via mise (shared global).
log_info "android-sdk: pinning JDK (java@temurin-17) via mise"
mise use -g java@temurin-17

# Honor an existing ANDROID_HOME; default to the conventional location.
ANDROID_HOME="${ANDROID_HOME:-${HOME}/Android/Sdk}"
license_marker="${ANDROID_HOME}/licenses/android-sdk-license"
adb_bin="${ANDROID_HOME}/platform-tools/adb"

# Idempotent: skip the whole SDK provisioning when the license marker AND adb
# are already present (a prior run completed successfully).
if [[ -f "${license_marker}" && -x "${adb_bin}" ]]; then
  log_skip "android-sdk: SDK already provisioned (${ANDROID_HOME}) — skipping"
  log_ok "android-sdk: ready"
  exit 0
fi

# Download + unzip the pinned command-line tools into cmdline-tools/latest/.
cmdline_tools_dir="${ANDROID_HOME}/cmdline-tools/latest"
if [[ ! -x "${cmdline_tools_dir}/bin/sdkmanager" ]]; then
  log_info "android-sdk: fetching command-line tools (${CMDLINE_TOOLS_VERSION})"
  tmp_zip="$(mktemp --suffix=.zip)"
  curl -fsSL -o "${tmp_zip}" "${CMDLINE_TOOLS_URL}"
  # The archive expands to a top-level cmdline-tools/ dir; place its contents at
  # cmdline-tools/latest/ (the layout sdkmanager expects).
  tmp_extract="$(mktemp -d)"
  unzip -q -o "${tmp_zip}" -d "${tmp_extract}"
  mkdir -p "${cmdline_tools_dir}"
  if [[ -d "${tmp_extract}/cmdline-tools" ]]; then
    cp -a "${tmp_extract}/cmdline-tools/." "${cmdline_tools_dir}/"
  else
    cp -a "${tmp_extract}/." "${cmdline_tools_dir}/"
  fi
  rm -rf "${tmp_zip}" "${tmp_extract}"
fi

# Prepend the cmdline-tools bin to PATH so a real install resolves sdkmanager,
# but call it by BARE NAME so test stubs on PATH win when the unzip is faked.
export PATH="${cmdline_tools_dir}/bin:${PATH}"
export ANDROID_HOME ANDROID_SDK_ROOT="${ANDROID_HOME}"

log_info "android-sdk: installing pinned SDK packages via sdkmanager"
sdkmanager "platform-tools" "platforms;android-35" "build-tools;36.0.0" "cmdline-tools;latest"

log_info "android-sdk: accepting SDK licenses (unattended)"
# `yes` feeds an unattended "y" to each license prompt; `head` bounds the stream
# so the producer closes (SIGPIPE) once sdkmanager has consumed all prompts.
# `yes` is then reaped with status 141 (128+SIGPIPE); tolerate it without
# tripping `set -o pipefail`/`-e`.
{ yes 2>/dev/null | head -n 100 | sdkmanager --licenses; } || true

log_ok "android-sdk: ready"
