#!/usr/bin/env bash
# modules/obsidian-sync/verify.sh — idempotency guard for obsidian-sync.
# GREEN iff the dedicated key + ssh alias + cloned vault + Obsidian registration +
# Git-plugin seed + systemd units are all present. Read-only; no prompts.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/vault.sh"

key="$(vault_key)"
dir="$(vault_dir)"
cfg="${HOME}/.ssh/config"
ob_flatpak="${HOME}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
data="${dir}/.obsidian/plugins/obsidian-git/data.json"
ud="${HOME}/.config/systemd/user"

[[ -f "${key}" ]] || exit 1
grep -q '^Host notes-vault.github.com' "${cfg}" 2>/dev/null || exit 1
[[ -d "${dir}/.git" ]] || exit 1
[[ -f "${ob_flatpak}" ]] || exit 1
command -v jq >/dev/null 2>&1 || exit 1
jq -e --arg p "${dir}" 'any(.vaults[]?; .path == $p and .open == true)' "${ob_flatpak}" >/dev/null 2>&1 || exit 1
[[ -f "${data}" ]] || exit 1
[[ -f "${ud}/devboost-vault-sync.service" && -f "${ud}/devboost-vault-sync.timer" ]] || exit 1

exit 0
