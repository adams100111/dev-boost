#!/usr/bin/env bash
# modules/dotnet-sdk/install.sh — install the .NET 10 LTS SDK from Fedora in-distro.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (skip when a 10.* SDK is already listed); non-interactive.
#
# Pin (in-repo source of truth, Principle III; context7-verified 2026-06): .NET 10 LTS
# (.NET 8/9 reach EOL Nov 2026 — not pinned). No Microsoft prod repo needed on Fedora 44.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# Idempotent: skip if dotnet is present AND already lists a 10.* SDK.
if have dotnet && dotnet --list-sdks 2>/dev/null | grep -qE '^10\.'; then
  log_skip "dotnet-sdk: a 10.* SDK is already installed — skipping"
  exit 0
fi

log_info "dotnet-sdk: installing .NET 10 LTS SDK (dotnet-sdk-10.0)"
sudo dnf install -y dotnet-sdk-10.0

log_ok "dotnet-sdk: installed"
