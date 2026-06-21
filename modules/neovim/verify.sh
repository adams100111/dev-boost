#!/usr/bin/env bash
# modules/neovim/verify.sh — idempotency guard for the neovim module.
# GREEN iff `nvim` is on PATH. No prompts; read-only.
set -Eeuo pipefail

command -v nvim >/dev/null 2>&1 || exit 1
exit 0
