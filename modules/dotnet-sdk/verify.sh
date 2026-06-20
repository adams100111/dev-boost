#!/usr/bin/env bash
# modules/dotnet-sdk/verify.sh — idempotency guard for the dotnet-sdk module.
# GREEN iff `dotnet` is on PATH AND `dotnet --list-sdks` reports a 10.* SDK.
# No prompts; read-only.
set -Eeuo pipefail

command -v dotnet >/dev/null 2>&1 || exit 1
dotnet --list-sdks 2>/dev/null | grep -qE '^10\.' || exit 1

exit 0
