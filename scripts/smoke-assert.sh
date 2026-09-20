#!/bin/sh
# scripts/smoke-assert.sh — guest-side post-install smoke checks (design §9.5, Task 6/7).
# Runs INSIDE a guest (a macOS tart VM or a Linux CI container/runner) right after
# `get.sh <profiles>` / `devboost install <profiles>` has provisioned it. POSIX sh so it
# runs unmodified on every guest — no bashisms.
#
# Usage: sh smoke-assert.sh <profiles...>
#
# `devboost`, `herdr` and `glow` are resolved from THIS shell's PATH, so run it from a
# fresh login shell started after the install (the macOS VM leg: a second `zsh -lc`), or
# with the source venv on PATH (the Linux legs: under `uv run`).
#
# Checks (every one runs; every failure is printed, not just the first):
#   - `devboost` is on PATH, and `devboost verify <profiles>` exits 0
#   - `herdr --version` reports 0.9.1
#   - `glow` is on PATH
#   - `devboost verify herdr-plugins` exits 0
#   - the login shell starts clean: no stderr from `zsh -lic exit` (Darwin) /
#     `bash -lic exit` (else), ignoring the job-control notices an interactive shell
#     prints when it has no controlling tty (CI steps, `tart exec`, `sudo -u`)
#
# Exit 0 if every check passes, 1 otherwise.
set -eu

fail=0
note() { printf 'smoke-assert: FAIL: %s\n' "$1" >&2; fail=1; }

have_devboost=1
if ! command -v devboost >/dev/null 2>&1; then
  note "devboost not on PATH (PATH=${PATH})"
  have_devboost=0
elif ! devboost verify "$@" >/dev/null 2>&1; then
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

if [ "${have_devboost}" = 1 ] && ! devboost verify herdr-plugins >/dev/null 2>&1; then
  note "devboost verify herdr-plugins"
fi

# tty_noise — drop what an interactive shell with no controlling tty always prints on
# stderr, so only real startup errors remain: bash's "cannot set terminal process group
# … Inappropriate ioctl for device" / "no job control in this shell", a login shell's
# "logout", and blank lines.
tty_noise() {
  grep -v -e 'cannot set terminal process group' -e 'no job control in this shell' \
    -e '^logout$' -e '^[[:space:]]*$' || true
}

os="$(uname -s)"
if [ "${os}" = "Darwin" ]; then
  shell_desc="zsh -lic exit"
  shell_err="$( (zsh -lic exit 2>&1 >/dev/null </dev/null || true) | tty_noise)"
else
  shell_desc="bash -lic exit"
  shell_err="$( (bash -lic exit 2>&1 >/dev/null </dev/null || true) | tty_noise)"
fi
if [ -n "${shell_err}" ]; then
  note "${shell_desc} wrote to stderr: ${shell_err}"
fi

# A silent pass is indistinguishable from a smoke that never ran: say so explicitly, so a
# green rehearsal log carries positive evidence rather than an absence of FAIL lines.
if [ "${fail}" -eq 0 ]; then
  printf 'smoke-assert: all checks passed (%s)\n' "$*"
fi

exit "${fail}"
