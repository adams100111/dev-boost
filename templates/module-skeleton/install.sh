#!/usr/bin/env bash
# modules/__NAME__/install.sh — escape-hatch installer for __NAME__.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME. No prompts; idempotent; verify-guarded.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# TODO: implement __NAME__ install (use have/need_cmd/log_info/log_ok/die from lib/log.sh+pkg.sh).
log_ok "__NAME__: installed"
