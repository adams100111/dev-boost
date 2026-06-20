#!/usr/bin/env bash
# modules/mise/install.sh — install mise + migrate nvm/sdkman init blocks.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (safe to re-run). Never writes repo config/mise.toml.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

# ---------------------------------------------------------------------------
# Step 1: ensure mise is installed
# ---------------------------------------------------------------------------
need_cmd mise mise

# ---------------------------------------------------------------------------
# Step 2: conditional, idempotent nvm → mise migration
# ---------------------------------------------------------------------------
_migrate_nvm() {
  local nvm_dir="${HOME}/.nvm"
  local bashrc="${HOME}/.bashrc"

  [[ -d "${nvm_dir}" ]] || return 0

  # Comment out the nvm init block — idempotent: skip if migration note already present.
  if [[ -f "${bashrc}" ]] && grep -qF "# BEGIN NVM" "${bashrc}"; then
    if grep -qF "devboost: migrated nvm init to mise" "${bashrc}"; then
      log_skip "mise: nvm init block already migrated in ${bashrc}"
    else
      log_info "mise: commenting out nvm init block in ${bashrc}"
      comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
      printf '# devboost: migrated nvm init to mise (%s)\n' "$(date +%Y-%m-%d)" >> "${bashrc}"
    fi
  fi

  # Resolve node version from nvm alias/default.
  local alias_file="${nvm_dir}/alias/default"
  if [[ ! -f "${alias_file}" ]]; then
    log_info "mise: ~/.nvm present but no alias/default — skipping mise use node"
    return 0
  fi

  local node_ver
  node_ver="$(tr -d '[:space:]' < "${alias_file}")"
  if [[ -z "${node_ver}" ]]; then
    log_info "mise: ~/.nvm/alias/default is empty — skipping mise use node"
    return 0
  fi

  log_info "mise: pinning node@${node_ver} in user global mise config"
  mise use -g "node@${node_ver}"
}

_migrate_sdkman() {
  local sdkman_dir="${HOME}/.sdkman"
  local bashrc="${HOME}/.bashrc"

  [[ -d "${sdkman_dir}" ]] || return 0

  # Comment out the sdkman init block — idempotent: skip if migration note already present.
  if [[ -f "${bashrc}" ]] && grep -qF "# BEGIN SDKMAN" "${bashrc}"; then
    if grep -qF "devboost: migrated sdkman init to mise" "${bashrc}"; then
      log_skip "mise: sdkman init block already migrated in ${bashrc}"
    else
      log_info "mise: commenting out sdkman init block in ${bashrc}"
      comment_block "${bashrc}" "# BEGIN SDKMAN" "# END SDKMAN"
      printf '# devboost: migrated sdkman init to mise (%s)\n' "$(date +%Y-%m-%d)" >> "${bashrc}"
    fi
  fi

  # Resolve java version from sdkman candidates/java/current symlink.
  local current_link="${sdkman_dir}/candidates/java/current"
  if [[ ! -L "${current_link}" && ! -d "${current_link}" ]]; then
    log_info "mise: ~/.sdkman present but no candidates/java/current — skipping mise use java"
    return 0
  fi

  local java_ver
  java_ver="$(basename "$(readlink -f "${current_link}")")"
  if [[ -z "${java_ver}" || "${java_ver}" == "current" ]]; then
    log_info "mise: could not resolve sdkman java version — skipping mise use java"
    return 0
  fi

  log_info "mise: pinning java@${java_ver} in user global mise config"
  mise use -g "java@${java_ver}"
}

_migrate_nvm
_migrate_sdkman

log_ok "mise: setup complete"
