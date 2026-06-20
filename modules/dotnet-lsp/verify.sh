#!/usr/bin/env bash
# modules/dotnet-lsp/verify.sh — idempotency guard for the dotnet-lsp module.
# GREEN iff csharp-ls resolves (on PATH or at ~/.dotnet/tools/csharp-ls) AND
# lsp.csharp is present and enabled in ~/.config/fresh/config.json.
# No prompts; read-only.
set -Eeuo pipefail

config="${HOME}/.config/fresh/config.json"
csharp_ls="${HOME}/.dotnet/tools/csharp-ls"

[[ -f "${config}" ]] || exit 1
command -v jq >/dev/null 2>&1 || exit 1

# csharp-ls must resolve either on PATH or via its dotnet-tool absolute path.
command -v csharp-ls >/dev/null 2>&1 || [[ -x "${csharp_ls}" ]] || exit 1

# lsp.csharp must be present and enabled.
jq -e '.lsp.csharp.enabled == true' "${config}" >/dev/null 2>&1 || exit 1

exit 0
