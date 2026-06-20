#!/usr/bin/env bash
# modules/web-runtimes/verify.sh — idempotency guard for the web-runtimes module.
# GREEN iff node, pnpm, and bun all resolve via `mise which`.
# No prompts; read-only.
set -Eeuo pipefail

command -v mise >/dev/null 2>&1 || exit 1

mise which node >/dev/null 2>&1 || exit 1
mise which pnpm >/dev/null 2>&1 || exit 1
mise which bun  >/dev/null 2>&1 || exit 1

exit 0
