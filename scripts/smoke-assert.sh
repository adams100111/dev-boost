#!/bin/sh
# scripts/smoke-assert.sh — guest-side post-install smoke checks (design §9.5, Task 6/7).
# Runs INSIDE a guest (a macOS tart VM or a Linux CI container/runner) right after
# `get.sh <profiles>` / `devboost install <profiles>` has provisioned it. POSIX sh so it
# runs unmodified on every guest — no bashisms.
#
# Usage: sh smoke-assert.sh <profiles...>
#
# Checks (every one runs; every failure is printed, not just the first):
#   - `devboost verify <profiles>` exits 0
#   - `herdr --version` reports 0.9.1
#   - `glow` is on PATH
#   - `devboost verify herdr-plugins` exits 0
#   - the login shell starts clean: no stderr from `zsh -lic exit` (Darwin) /
#     `bash -lic exit` (else)
#
# Exit 0 if every check passes, 1 otherwise.
set -eu

fail=0
note() { printf 'smoke-assert: FAIL: %s\n' "$1" >&2; fail=1; }

if ! devboost verify "$@" >/dev/null 2>&1; then
  note "devboost verify $*"
fi

herdr_ver="$(herdr --version 2>/dev/null || true)"
case "${herdr_ver}" in
  *0.9.1*) ;;
  *) note "herdr --version (got '${herdr_ver}', want 0.9.1)" ;;
esac

if ! command -v glow >/dev/null 2>&1; then
  note "glow not on PATH"
fi

if ! devboost verify herdr-plugins >/dev/null 2>&1; then
  note "devboost verify herdr-plugins"
fi

os="$(uname -s)"
if [ "${os}" = "Darwin" ]; then
  shell_desc="zsh -lic exit"
  shell_err="$(zsh -lic exit 2>&1 >/dev/null || true)"
else
  shell_desc="bash -lic exit"
  shell_err="$(bash -lic exit 2>&1 >/dev/null || true)"
fi
if [ -n "${shell_err}" ]; then
  note "${shell_desc} wrote to stderr: ${shell_err}"
fi

exit "${fail}"
