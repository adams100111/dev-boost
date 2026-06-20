#!/usr/bin/env bash
# modules/devops-lsp/install.sh — provision fresh's DevOps language intelligence.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (jq-merge reconciles, never clobbers); non-interactive.
#
# Seeds the base config.json if absent (reusing the editors base template), then
# provisions each DevOps server as a mise-managed pinned tool and wires it into
# config.json via lib/fresh.sh.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/fresh.sh"

# fresh must exist before we wire language intelligence into its config (FR-014).
have fresh || die "devops-lsp: the fresh editor is not installed — cannot provision LSP"

config="${HOME}/.config/fresh/config.json"
base_template="${DEVBOOST_ROOT}/modules/fresh-lsp/config.base.json"
servers_tsv="${DEVBOOST_ROOT}/modules/devops-lsp/servers.tsv"

# Seed the base config only if absent (editors/fresh-lsp or chezmoi may own it).
if [[ ! -f "${config}" ]]; then
  log_info "devops-lsp: seeding base config ${config}"
  mkdir -p "$(dirname "${config}")"
  cp "${base_template}" "${config}"
else
  log_skip "devops-lsp: base config already present (${config})"
fi

# Provision each DevOps server row.
[[ -f "${servers_tsv}" ]] || die "devops-lsp: server list not found: ${servers_tsv}"
while IFS=$'\t' read -r lang cmd spec args || [[ -n "${lang}" ]]; do
  [[ -z "${lang}" || "${lang}" == \#* ]] && continue
  if [[ -n "${args:-}" ]]; then
    # shellcheck disable=SC2086 — args is an intentional space-separated argv slice.
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}" ${args}
  else
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}"
  fi
done < "${servers_tsv}"

log_ok "devops-lsp: DevOps language intelligence provisioned"
