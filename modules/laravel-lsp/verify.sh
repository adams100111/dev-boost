#!/usr/bin/env bash
# modules/laravel-lsp/verify.sh — idempotency guard for the laravel-lsp module.
# GREEN iff every Laravel-stack server tool resolves via `mise which` AND its
# lsp.<lang> entry is present and enabled in ~/.config/fresh/config.json.
# No prompts; read-only.
set -Eeuo pipefail

config="${HOME}/.config/fresh/config.json"
servers_tsv="${DEVBOOST_ROOT}/modules/laravel-lsp/servers.tsv"

[[ -f "${config}" ]] || exit 1
[[ -f "${servers_tsv}" ]] || exit 1
command -v mise >/dev/null 2>&1 || exit 1
command -v jq   >/dev/null 2>&1 || exit 1

while IFS=$'\t' read -r lang cmd spec args || [[ -n "${lang}" ]]; do
  [[ -z "${lang}" || "${lang}" == \#* ]] && continue
  # Tool must resolve via mise.
  mise which "${cmd}" >/dev/null 2>&1 || exit 1
  # lsp.<lang> must be present and enabled.
  jq -e --arg l "${lang}" '.lsp[$l].enabled == true' "${config}" >/dev/null 2>&1 || exit 1
done < "${servers_tsv}"

exit 0
