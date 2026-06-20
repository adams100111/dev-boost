#!/usr/bin/env bash
# modules/obsidian-sync/install.sh — unattended Obsidian↔GitHub vault sync (Spec 8).
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME, XDG_*.
# No prompts; idempotent (skip-if-present / seed-if-absent / merge-not-clobber); non-interactive.
#
# Reuses lib/secrets.sh (PAT/user) + lib/github.sh (deploy-key) + lib/vault.sh (feature helper).
# ZERO engine touch.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/secrets.sh"
source "${DEVBOOST_ROOT}/lib/github.sh"
source "${DEVBOOST_ROOT}/lib/vault.sh"

# US2 — dedicated repo-scoped key, isolated ssh alias, write deploy key, clone → ~/Vault.
vault_keygen
vault_ssh_alias
vault_register_deploy_key   # dies NAMED if the bootstrap PAT/user is absent (FR-012)
vault_clone

# US3 — register the vault so Obsidian opens it; pre-seed the Git plugin; vault hygiene.
vault_obsidian_register
vault_seed_git_plugin
vault_gitignore

# US4 — daily push backstop + shell env.
vault_systemd_units
vault_shell_env

log_ok "obsidian-sync: vault provisioned, registered, and sync-scheduled"
