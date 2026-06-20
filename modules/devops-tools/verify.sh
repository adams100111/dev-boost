#!/usr/bin/env bash
# modules/devops-tools/verify.sh — idempotency guard for the devops-tools module.
# GREEN iff tofu, kubectl, helm, and k9s all resolve via `mise which`.
# No prompts; read-only.
set -Eeuo pipefail

command -v mise >/dev/null 2>&1 || exit 1

mise which tofu    >/dev/null 2>&1 || exit 1
mise which kubectl >/dev/null 2>&1 || exit 1
mise which helm    >/dev/null 2>&1 || exit 1
mise which k9s     >/dev/null 2>&1 || exit 1

exit 0
