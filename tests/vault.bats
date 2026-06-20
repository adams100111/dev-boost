load test_helper
load fixtures/base/stubs

# Unit tests for lib/vault.sh (Spec 8). Functions exercised in isolation against the
# stub harness (ssh-keygen/git/systemctl/loginctl/curl-GitHub-API stubs; real jq).

setup() {
  load_lib log.sh
  base_setup
  source "${DEVBOOST_ROOT}/lib/secrets.sh"
  source "${DEVBOOST_ROOT}/lib/github.sh"
  source "${DEVBOOST_ROOT}/lib/vault.sh"
  export GITHUB_API="https://api.github.com"
  # Hermetic secrets accessors (override the age/bundle-backed ones).
  secrets_user() { printf 'testuser\n'; }
  secrets_pat()  { printf 'ghp_TESTfaketoken0000000000000000000001\n'; }
}

teardown() { base_teardown; }

# --- vault_keygen ---------------------------------------------------------
@test "vault_keygen: generates the dedicated key when absent" {
  [ ! -f "${HOME}/.ssh/notes_vault_ed25519" ]
  run vault_keygen
  [ "$status" -eq 0 ]
  [ -f "${HOME}/.ssh/notes_vault_ed25519" ]
  [ -f "${HOME}/.ssh/notes_vault_ed25519.pub" ]
  grep -q 'ed25519' "${STUB_SSH_KEYGEN_LOG}"
}

@test "vault_keygen: idempotent — does not regenerate an existing key" {
  mkdir -p "${HOME}/.ssh"; printf 'existing\n' > "${HOME}/.ssh/notes_vault_ed25519"
  run vault_keygen
  [ "$status" -eq 0 ]
  [ "$(cat "${HOME}/.ssh/notes_vault_ed25519")" = "existing" ]
  [ ! -s "${STUB_SSH_KEYGEN_LOG}" ]
}

# --- vault_ssh_alias ------------------------------------------------------
@test "vault_ssh_alias: writes an isolated host block with IdentitiesOnly" {
  run vault_ssh_alias
  [ "$status" -eq 0 ]
  grep -q '^Host notes-vault.github.com' "${HOME}/.ssh/config"
  grep -q 'IdentityFile .*/.ssh/notes_vault_ed25519' "${HOME}/.ssh/config"
  grep -q 'IdentitiesOnly yes' "${HOME}/.ssh/config"
}

@test "vault_ssh_alias: idempotent — re-run does not duplicate the block" {
  vault_ssh_alias; vault_ssh_alias
  [ "$(grep -c '^Host notes-vault.github.com' "${HOME}/.ssh/config")" -eq 1 ]
}

@test "vault_ssh_alias: preserves a pre-existing unrelated ssh config block" {
  mkdir -p "${HOME}/.ssh"
  printf 'Host example\n  User me\n' > "${HOME}/.ssh/config"
  vault_ssh_alias
  grep -q '^Host example' "${HOME}/.ssh/config"
  grep -q '^Host notes-vault.github.com' "${HOME}/.ssh/config"
}

# --- vault_register_deploy_key -------------------------------------------
@test "vault_register_deploy_key: POSTs a WRITE deploy key" {
  mkdir -p "${HOME}/.ssh"; printf 'ssh-ed25519 AAAA testkey\n' > "${HOME}/.ssh/notes_vault_ed25519.pub"
  run vault_register_deploy_key
  [ "$status" -eq 0 ]
  grep -q -- '-X POST' "${STUB_CURL_LOG}"
  grep -q '/repos/testuser/notes-vault/keys' "${STUB_CURL_LOG}"
}

@test "vault_register_deploy_key: dedups when the key body already exists" {
  mkdir -p "${HOME}/.ssh"
  printf 'ssh-ed25519 AAAADUP devboost-vault\n' > "${HOME}/.ssh/notes_vault_ed25519.pub"
  export STUB_GH_DEPLOY_KEYS='[{"id":9,"title":"old","key":"ssh-ed25519 AAAADUP devboost-vault"}]'
  run vault_register_deploy_key
  [ "$status" -eq 0 ]
  ! grep -q -- '-X POST' "${STUB_CURL_LOG}"
}

@test "vault_register_deploy_key: dies when PAT is absent" {
  secrets_pat() { printf '\n'; }
  mkdir -p "${HOME}/.ssh"; printf 'k\n' > "${HOME}/.ssh/notes_vault_ed25519.pub"
  run vault_register_deploy_key
  [ "$status" -ne 0 ]
  [[ "$output" == *"PAT"* ]]
}

# --- vault_clone ----------------------------------------------------------
@test "vault_clone: clones over the isolated alias when ~/Vault absent" {
  run vault_clone
  [ "$status" -eq 0 ]
  grep -q 'clone git@notes-vault.github.com:testuser/notes-vault.git' "${STUB_GIT_LOG}"
}

@test "vault_clone: skips when ~/Vault/.git already present" {
  mkdir -p "${HOME}/Vault/.git"
  run vault_clone
  [ "$status" -eq 0 ]
  ! grep -q 'clone' "${STUB_GIT_LOG}"
}

# --- vault_obsidian_register ---------------------------------------------
@test "vault_obsidian_register: registers ~/Vault open:true in the flatpak config" {
  run vault_obsidian_register
  [ "$status" -eq 0 ]
  cfg="${HOME}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
  [ -f "${cfg}" ]
  [ "$(jq -r '[.vaults[] | select(.path=="'"${HOME}"'/Vault") | .open][0]' "${cfg}")" = "true" ]
}

@test "vault_obsidian_register: native config written only when its dir exists" {
  run vault_obsidian_register
  [ ! -f "${HOME}/.config/obsidian/obsidian.json" ]
  mkdir -p "${HOME}/.config/obsidian"
  vault_obsidian_register
  [ -f "${HOME}/.config/obsidian/obsidian.json" ]
}

@test "vault_obsidian_register: preserves a pre-existing vault entry" {
  cfg="${HOME}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
  mkdir -p "$(dirname "${cfg}")"
  printf '{"vaults":{"abc":{"path":"/home/x/Other","open":false}}}\n' > "${cfg}"
  vault_obsidian_register
  [ "$(jq -r '.vaults.abc.path' "${cfg}")" = "/home/x/Other" ]
  [ "$(jq -r '[.vaults[] | select(.path=="'"${HOME}"'/Vault")] | length' "${cfg}")" = "1" ]
}

# --- vault_seed_git_plugin -----------------------------------------------
@test "vault_seed_git_plugin: seeds data.json with verified keys + enables plugin" {
  run vault_seed_git_plugin
  [ "$status" -eq 0 ]
  data="${HOME}/Vault/.obsidian/plugins/obsidian-git/data.json"
  [ "$(jq -r '.syncMethod' "${data}")" = "rebase" ]
  [ "$(jq -r '.autoSaveInterval' "${data}")" = "10" ]
  [ "$(jq -r '.autoPullOnBoot' "${data}")" = "true" ]
  [ "$(jq -r 'index("obsidian-git") != null' "${HOME}/Vault/.obsidian/community-plugins.json")" = "true" ]
}

@test "vault_seed_git_plugin: seed-if-absent — never overwrites user data.json" {
  data="${HOME}/Vault/.obsidian/plugins/obsidian-git/data.json"
  mkdir -p "$(dirname "${data}")"; printf '{"syncMethod":"merge","mine":1}\n' > "${data}"
  vault_seed_git_plugin
  [ "$(jq -r '.syncMethod' "${data}")" = "merge" ]
  [ "$(jq -r '.mine' "${data}")" = "1" ]
}

@test "vault_seed_git_plugin: community-plugins not duplicated on re-run" {
  vault_seed_git_plugin; vault_seed_git_plugin
  [ "$(jq -r '[.[]|select(.=="obsidian-git")]|length' "${HOME}/Vault/.obsidian/community-plugins.json")" = "1" ]
}

# --- vault_gitignore ------------------------------------------------------
@test "vault_gitignore: excludes workspace + trash, idempotently" {
  vault_gitignore; vault_gitignore
  gi="${HOME}/Vault/.gitignore"
  [ "$(grep -c '.obsidian/workspace\*.json' "${gi}")" -eq 1 ]
  [ "$(grep -c '.trash/' "${gi}")" -eq 1 ]
}

# --- vault_systemd_units --------------------------------------------------
@test "vault_systemd_units: writes oneshot service + daily persistent timer and enables them" {
  run vault_systemd_units
  [ "$status" -eq 0 ]
  svc="${HOME}/.config/systemd/user/devboost-vault-sync.service"
  tmr="${HOME}/.config/systemd/user/devboost-vault-sync.timer"
  grep -q 'Type=oneshot' "${svc}"
  grep -q 'pull --rebase --autostash' "${svc}"
  grep -q 'vault-sync.log' "${svc}"
  grep -q 'OnCalendar=daily' "${tmr}"
  grep -q 'Persistent=true' "${tmr}"
  grep -q 'enable --now devboost-vault-sync.timer' "${STUB_SYSTEMCTL_LOG}"
  grep -q 'enable-linger' "${STUB_LOGINCTL_LOG}"
}

@test "vault_systemd_units: idempotent — re-run keeps a single unit pair" {
  vault_systemd_units; vault_systemd_units
  [ -f "${HOME}/.config/systemd/user/devboost-vault-sync.service" ]
  [ -f "${HOME}/.config/systemd/user/devboost-vault-sync.timer" ]
}

# --- vault_shell_env ------------------------------------------------------
@test "vault_shell_env: exports VAULT_DIR via an idempotent marker block" {
  vault_shell_env; vault_shell_env
  [ "$(grep -c '# BEGIN devboost-vault-env' "${HOME}/.bashrc")" -eq 1 ]
  grep -q 'export VAULT_DIR=' "${HOME}/.bashrc"
}

@test "vault_shell_env: preserves pre-existing bashrc content" {
  printf 'echo keepme\n' > "${HOME}/.bashrc"
  vault_shell_env
  grep -q 'echo keepme' "${HOME}/.bashrc"
}
