#!/usr/bin/env bash
# modules/android-sdk/verify.sh — idempotency guard for the android-sdk module.
# GREEN iff the platform-tools adb binary exists under ANDROID_HOME AND mise can
# resolve java (RN's pinned JDK). No prompts; read-only.
set -Eeuo pipefail

ANDROID_HOME="${ANDROID_HOME:-${HOME}/Android/Sdk}"

[[ -x "${ANDROID_HOME}/platform-tools/adb" ]] || exit 1
command -v mise >/dev/null 2>&1 || exit 1
mise which java >/dev/null 2>&1 || exit 1

exit 0
