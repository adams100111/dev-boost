#!/usr/bin/env bash
# modules/aspire/install.sh — install the Aspire CLI as a global dotnet tool.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (skip when aspire already present); non-interactive.
#
# Aspire is now a standalone CLI (`dotnet tool install -g Aspire.Cli`, binary `aspire`);
# the old `dotnet workload install aspire` path is deprecated (context7-verified 2026-06).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if have aspire; then
  log_skip "aspire: already installed — skipping"
  exit 0
fi

log_info "aspire: installing the Aspire CLI (dotnet tool install -g Aspire.Cli)"
dotnet tool install -g Aspire.Cli

log_ok "aspire: installed"
