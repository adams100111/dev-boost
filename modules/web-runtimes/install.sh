#!/usr/bin/env bash
# modules/web-runtimes/install.sh — provision the Web stack's JS/TS runtimes.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (`mise use -g` reconciles a pinned global set).
#
# Installs Node 22 LTS + pnpm + bun as mise-managed, version-pinned global tools
# in a single declaration. Pins ARE the in-repo source of truth (Principle III).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

have mise || die "web-runtimes: mise is not installed — cannot provision runtimes"

# One combined, pinned declaration (idempotent; reconciles the global tool set).
mise use -g node@22 pnpm@11.8.0 bun@1.3.14 \
  || die "web-runtimes: 'mise use -g node@22 pnpm@11.8.0 bun@1.3.14' failed"

log_ok "web-runtimes: node@22 pnpm@11.8.0 bun@1.3.14 provisioned"
