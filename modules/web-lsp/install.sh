#!/usr/bin/env bash
# modules/web-lsp/install.sh — provision the Web stack's fresh language intelligence.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (jq-merge reconciles, never clobbers); non-interactive.
#
# Wires the Web stack servers/formatter (TS/ESLint/Tailwind LSP + prettier) into
# fresh's config.json as mise-managed, pinned tools via lib/fresh.sh. Seeds the
# base config only if absent (editors' fresh-lsp normally owns it).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/fresh.sh"

# fresh must exist before we wire language intelligence into its config (FR-014).
have fresh || die "web-lsp: the fresh editor is not installed — cannot provision LSP"

config="${HOME}/.config/fresh/config.json"
base_template="${DEVBOOST_ROOT}/modules/fresh-lsp/config.base.json"
servers_tsv="${DEVBOOST_ROOT}/modules/web-lsp/servers.tsv"

# Seed the base config only if absent (editors/fresh-lsp or dotfiles may own it).
if [[ ! -f "${config}" ]]; then
  log_info "web-lsp: seeding base config ${config}"
  mkdir -p "$(dirname "${config}")"
  cp "${base_template}" "${config}"
else
  log_skip "web-lsp: base config already present (${config})"
fi

# Provision each Web stack server/formatter row.
[[ -f "${servers_tsv}" ]] || die "web-lsp: server list not found: ${servers_tsv}"
while IFS=$'\t' read -r lang cmd spec args || [[ -n "${lang}" ]]; do
  [[ -z "${lang}" || "${lang}" == \#* ]] && continue
  if [[ -n "${args:-}" ]]; then
    # shellcheck disable=SC2086 — args is an intentional space-separated argv slice.
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}" ${args}
  else
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}"
  fi
done < "${servers_tsv}"

log_ok "web-lsp: Web stack language intelligence provisioned"
