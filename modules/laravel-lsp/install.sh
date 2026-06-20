#!/usr/bin/env bash
# modules/laravel-lsp/install.sh — wire the Laravel stack's PHP language
# intelligence (intelephense, global, mise-pinned) into fresh's config.json.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (jq-merge reconciles, never clobbers); non-interactive.
#
# Pint (the PHP formatter) is a per-project composer dev-dependency and is wired
# in templates/laravel/.fresh/config.json (run via ddev) — NOT here as a global.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/fresh.sh"

# fresh must exist before we wire language intelligence into its config (FR-013/014).
have() { command -v "$1" >/dev/null 2>&1; }
have fresh || die "laravel-lsp: the fresh editor is not installed — cannot provision LSP"

config="${HOME}/.config/fresh/config.json"
base_template="${DEVBOOST_ROOT}/modules/fresh-lsp/config.base.json"
servers_tsv="${DEVBOOST_ROOT}/modules/laravel-lsp/servers.tsv"

# Seed the base config only if absent (editors/fresh-lsp normally owns it; seed
# defensively so this stack works even when run before the editors profile).
if [[ ! -f "${config}" ]]; then
  log_info "laravel-lsp: seeding base config ${config}"
  mkdir -p "$(dirname "${config}")"
  cp "${base_template}" "${config}"
else
  log_skip "laravel-lsp: base config already present (${config})"
fi

# Provision each Laravel-stack server row.
[[ -f "${servers_tsv}" ]] || die "laravel-lsp: server list not found: ${servers_tsv}"
while IFS=$'\t' read -r lang cmd spec args || [[ -n "${lang}" ]]; do
  [[ -z "${lang}" || "${lang}" == \#* ]] && continue
  if [[ -n "${args:-}" ]]; then
    # shellcheck disable=SC2086 — args is an intentional space-separated argv slice.
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}" ${args}
  else
    fresh_lsp_provision "${lang}" "${cmd}" "${spec}"
  fi
done < "${servers_tsv}"

log_ok "laravel-lsp: PHP language intelligence (intelephense) provisioned"
