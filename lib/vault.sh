# lib/vault.sh — Obsidian vault sync helper (Spec 8 apps-and-obsidian).
# Source-only; no side effects on source. Feature-local data-layer support (like lib/fresh.sh),
# NOT engine. Depends on lib/log.sh (die/log_*); deploy-key registration additionally uses
# lib/github.sh (gh_add_deploy_key) + lib/secrets.sh (secrets_pat/secrets_user).
# All external commands (git, ssh-keygen, jq, systemctl, loginctl, hostname, id) are PATH-stubbable.

# --- resolvers (env-overridable; the in-repo defaults are the source of truth) -------------
vault_dir()      { printf '%s\n' "${VAULT_DIR:-${HOME}/Vault}"; }
vault_key()      { printf '%s\n' "${HOME}/.ssh/notes_vault_ed25519"; }
vault_repo()     { printf '%s\n' "${DEVBOOST_VAULT_REPO:-notes-vault}"; }
vault_ssh_host() { printf '%s\n' "notes-vault.github.com"; }

# --- US2: dedicated key + isolated ssh alias + deploy-key registration + clone -------------

# vault_keygen — generate the repo-scoped ed25519 key if absent (passphrase-less, unattended).
vault_keygen() {
  local key; key="$(vault_key)"
  if [[ -f "${key}" ]]; then
    log_skip "vault: deploy key already present (${key})"
    return 0
  fi
  mkdir -p "${HOME}/.ssh"; chmod 700 "${HOME}/.ssh"
  log_info "vault: generating repo-scoped deploy key ${key}"
  ssh-keygen -t ed25519 -N "" -C "devboost-vault:$(hostname)" -f "${key}" \
    || die "vault: ssh-keygen failed for ${key}"
  chmod 600 "${key}"
}

# vault_ssh_alias — ensure an isolated, marker-delimited Host block for the vault remote.
vault_ssh_alias() {
  local cfg="${HOME}/.ssh/config" host; host="$(vault_ssh_host)"
  mkdir -p "${HOME}/.ssh"; chmod 700 "${HOME}/.ssh"; touch "${cfg}"; chmod 600 "${cfg}"
  local begin="# BEGIN devboost-vault" end="# END devboost-vault"
  local block="${begin}
Host ${host}
  HostName github.com
  IdentityFile $(vault_key)
  IdentitiesOnly yes
${end}"
  if grep -qE "^# BEGIN devboost-vault" "${cfg}" 2>/dev/null; then
    local tmp; tmp="$(mktemp)"
    awk -v b="${block}" '
      /^# BEGIN devboost-vault/ { print b; skip=1; next }
      skip && /^# END devboost-vault/ { skip=0; next }
      skip { next }
      { print }
    ' "${cfg}" > "${tmp}" && mv "${tmp}" "${cfg}"
  else
    printf '\n%s\n' "${block}" >> "${cfg}"
  fi
}

# vault_register_deploy_key — register the public key as a WRITE deploy key (idempotent via gh_add_deploy_key).
vault_register_deploy_key() {
  local owner repo pat; owner="$(secrets_user)"; repo="$(vault_repo)"
  [[ -n "${owner}" ]] || die "vault: no GitHub user available (secrets) — cannot register deploy key"
  pat="$(secrets_pat)"
  [[ -n "${pat}" ]] || die "vault: no GitHub PAT available (secrets) — cannot register deploy key"
  export GITHUB_PAT="${pat}"
  gh_add_deploy_key "${owner}" "${repo}" "$(vault_key).pub" "devboost-vault:$(hostname)" \
    || die "vault: deploy-key registration failed for ${owner}/${repo}"
}

# vault_clone — clone the vault repo to ~/Vault over the isolated alias, if absent.
vault_clone() {
  local dir owner; dir="$(vault_dir)"
  if [[ -d "${dir}/.git" ]]; then
    log_skip "vault: ${dir} already cloned"
    return 0
  fi
  owner="$(secrets_user)"
  [[ -n "${owner}" ]] || die "vault: no GitHub user available (secrets) — cannot clone"
  log_info "vault: cloning ${owner}/$(vault_repo) → ${dir}"
  git clone "git@$(vault_ssh_host):${owner}/$(vault_repo).git" "${dir}" \
    || die "vault: clone failed (git@$(vault_ssh_host):${owner}/$(vault_repo).git)"
}

# --- US3: Obsidian vault registration + Git-plugin seed + gitignore hygiene ----------------

# _vault_register_one <obsidian.json path> — jq-merge ~/Vault (open:true), dedup by path, preserve others.
_vault_register_one() {
  local cfg="$1" dir id tmp; dir="$(vault_dir)"
  mkdir -p "$(dirname "${cfg}")"
  [[ -f "${cfg}" ]] || printf '{"vaults":{}}\n' > "${cfg}"
  id="$(printf '%s' "${dir}" | cksum | cut -d' ' -f1)"
  tmp="$(mktemp)"
  jq --arg p "${dir}" --arg id "${id}" '
    .vaults = (.vaults // {})
    | (([.vaults | to_entries[] | select(.value.path == $p) | .key])[0]) as $existing
    | if $existing then .vaults[$existing].open = true
      else .vaults[$id] = {path: $p, ts: 0, open: true} end
  ' "${cfg}" > "${tmp}" && mv "${tmp}" "${cfg}" || { rm -f "${tmp}"; die "vault: failed to register vault in ${cfg}"; }
}

# vault_obsidian_register — Flatpak config always; native only if its dir exists.
vault_obsidian_register() {
  _vault_register_one "${HOME}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
  if [[ -d "${HOME}/.config/obsidian" ]]; then
    _vault_register_one "${HOME}/.config/obsidian/obsidian.json"
  fi
}

# vault_seed_git_plugin — seed obsidian-git data.json (seed-if-absent) + enable in community-plugins.json.
vault_seed_git_plugin() {
  local dir pdir data cpj tmp; dir="$(vault_dir)"
  pdir="${dir}/.obsidian/plugins/obsidian-git"; data="${pdir}/data.json"
  if [[ -f "${data}" ]]; then
    log_skip "vault: obsidian-git data.json present (seed-if-absent)"
  else
    mkdir -p "${pdir}"
    cat > "${data}" <<'JSON'
{
  "autoPullOnBoot": true,
  "autoBackupAfterFileChange": true,
  "autoSaveInterval": 10,
  "autoPullInterval": 10,
  "pullBeforePush": true,
  "syncMethod": "rebase",
  "commitMessage": "vault backup: {{date}}",
  "autoCommitMessage": "vault backup: {{date}}",
  "commitDateFormat": "YYYY-MM-DD HH:mm:ss"
}
JSON
  fi
  cpj="${dir}/.obsidian/community-plugins.json"
  mkdir -p "${dir}/.obsidian"
  [[ -f "${cpj}" ]] || printf '[]\n' > "${cpj}"
  if ! jq -e 'index("obsidian-git")' "${cpj}" >/dev/null 2>&1; then
    tmp="$(mktemp)"
    jq '. + ["obsidian-git"] | unique' "${cpj}" > "${tmp}" && mv "${tmp}" "${cpj}" \
      || { rm -f "${tmp}"; die "vault: failed to enable obsidian-git in ${cpj}"; }
  fi
}

# vault_gitignore — exclude local UI state + trash from the vault repo.
vault_gitignore() {
  local gi; gi="$(vault_dir)/.gitignore"
  mkdir -p "$(dirname "${gi}")"; touch "${gi}"
  grep -qxF '.obsidian/workspace*.json' "${gi}" || printf '%s\n' '.obsidian/workspace*.json' >> "${gi}"
  grep -qxF '.trash/' "${gi}" || printf '%s\n' '.trash/' >> "${gi}"
}

# --- US4: systemd --user daily push backstop + shell env -----------------------------------

# vault_systemd_units — write + enable the oneshot service and the daily persistent timer.
vault_systemd_units() {
  local ud="${HOME}/.config/systemd/user" dir logf; dir="$(vault_dir)"
  logf="${XDG_STATE_HOME:-${HOME}/.local/state}/devboost/vault-sync.log"
  mkdir -p "${ud}"
  cat > "${ud}/devboost-vault-sync.service" <<EOF
[Unit]
Description=devboost Obsidian vault sync (commit + pull --rebase + push)

[Service]
Type=oneshot
ExecStart=/bin/bash -lc 'mkdir -p "$(dirname "${logf}")"; { git -C "${dir}" add -A && git -C "${dir}" commit -m "vault backup: \$(date -Is)" --quiet || true; git -C "${dir}" pull --rebase --autostash && git -C "${dir}" push; } >> "${logf}" 2>&1'
EOF
  cat > "${ud}/devboost-vault-sync.timer" <<'EOF'
[Unit]
Description=devboost daily Obsidian vault sync

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF
  # Run without an active session (headless first boot); tolerate stub/no-systemd.
  loginctl enable-linger "$(id -un)" 2>/dev/null || true
  systemctl --user enable --now devboost-vault-sync.timer 2>/dev/null || true
}

# vault_shell_env — export VAULT_DIR via an idempotent marker block (do NOT clobber dotfiles) + XDG dir.
vault_shell_env() {
  local rc="${HOME}/.bashrc" dir udd; dir="$(vault_dir)"
  touch "${rc}"
  local begin="# BEGIN devboost-vault-env" end="# END devboost-vault-env"
  local block="${begin}
export VAULT_DIR=\"${dir}\"
${end}"
  if grep -qE "^# BEGIN devboost-vault-env" "${rc}" 2>/dev/null; then
    local tmp; tmp="$(mktemp)"
    awk -v b="${block}" '
      /^# BEGIN devboost-vault-env/ { print b; skip=1; next }
      skip && /^# END devboost-vault-env/ { skip=0; next }
      skip { next }
      { print }
    ' "${rc}" > "${tmp}" && mv "${tmp}" "${rc}"
  else
    printf '\n%s\n' "${block}" >> "${rc}"
  fi
  udd="${XDG_CONFIG_HOME:-${HOME}/.config}/user-dirs.dirs"
  mkdir -p "$(dirname "${udd}")"; touch "${udd}"
  grep -qE '^XDG_VAULT_DIR=' "${udd}" || printf 'XDG_VAULT_DIR="%s"\n' "${dir}" >> "${udd}"
}
