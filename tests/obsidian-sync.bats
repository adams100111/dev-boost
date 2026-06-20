load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# US2/US3/US4 — obsidian-sync module. Exercised end-to-end via install.sh against the stub
# harness: ssh-keygen/git/flatpak/systemctl/loginctl + curl-GitHub-API + a hermetic age/bundle.

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export GITHUB_API="https://api.github.com"
  export STUB_GIT_CLONE_CREATES_DIR=1
  # Hermetic secrets: a plaintext bundle + an `age -d` stub that emits it.
  export DEVBOOST_SECRETS="${BATS_TEST_TMPDIR}/bundle.json"
  export DEVBOOST_SECRETS_KEY="${BATS_TEST_TMPDIR}/age-key.txt"
  printf '{"GIT_USER":"testuser","GIT_EMAIL":"t@e.x","GITHUB_PAT":"ghp_TESTfaketoken0000000000000000000001"}\n' > "${DEVBOOST_SECRETS}"
  cat > "$(base_stub_dir)/age" <<'AGE'
#!/usr/bin/env bash
for a in "$@"; do [[ "$a" == "-d" ]] && { cat "${DEVBOOST_SECRETS}"; exit 0; }; done
exit 0
AGE
  chmod +x "$(base_stub_dir)/age"
}

teardown() { base_teardown; }

_run_sync() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_SECRETS='${DEVBOOST_SECRETS}'
    export DEVBOOST_SECRETS_KEY='${DEVBOOST_SECRETS_KEY}'
    export GITHUB_API='https://api.github.com'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_SSH_KEYGEN_LOG='${STUB_SSH_KEYGEN_LOG}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_LOGINCTL_LOG='${STUB_LOGINCTL_LOG}'
    export STUB_GIT_CLONE_CREATES_DIR=1
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    bash '${DEVBOOST_ROOT}/modules/obsidian-sync/install.sh'
  " 2>&1
}

_run_verify() {
  bash -c "export HOME='${HOME}'; export DEVBOOST_ROOT='${DEVBOOST_ROOT}'; bash '${DEVBOOST_ROOT}/modules/obsidian-sync/verify.sh'" 2>&1
}

# ===== US2: deploy key + ssh alias + clone =====
@test "obsidian-sync: generates the dedicated deploy key" {
  run _run_sync
  [ "$status" -eq 0 ]
  [ -f "${HOME}/.ssh/notes_vault_ed25519" ]
}

@test "obsidian-sync: writes isolated ssh alias (IdentitiesOnly)" {
  _run_sync
  grep -q '^Host notes-vault.github.com' "${HOME}/.ssh/config"
  grep -q 'IdentitiesOnly yes' "${HOME}/.ssh/config"
}

@test "obsidian-sync: registers a WRITE deploy key via the GitHub API" {
  _run_sync
  grep -q -- '-X POST' "${STUB_CURL_LOG}"
  grep -q '/repos/testuser/notes-vault/keys' "${STUB_CURL_LOG}"
}

@test "obsidian-sync: clones the vault over the isolated alias → ~/Vault" {
  _run_sync
  grep -q 'clone git@notes-vault.github.com:testuser/notes-vault.git' "${STUB_GIT_LOG}"
  [ -d "${HOME}/Vault/.git" ]
}

@test "obsidian-sync: dies (named) when the bootstrap PAT is absent" {
  printf '{"GIT_USER":"testuser","GIT_EMAIL":"t@e.x"}\n' > "${DEVBOOST_SECRETS}"
  run _run_sync
  [ "$status" -ne 0 ]
  [[ "$output" == *"PAT"* || "$output" == *"GITHUB_PAT"* ]]
}

# ===== US3: obsidian config + git plugin + gitignore =====
@test "obsidian-sync: registers ~/Vault open:true in the flatpak Obsidian config" {
  _run_sync
  cfg="${HOME}/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
  [ "$(jq -r 'any(.vaults[]?; .path=="'"${HOME}"'/Vault" and .open==true)' "${cfg}")" = "true" ]
}

@test "obsidian-sync: seeds the obsidian-git plugin with verified settings + enables it" {
  _run_sync
  data="${HOME}/Vault/.obsidian/plugins/obsidian-git/data.json"
  [ "$(jq -r '.syncMethod' "${data}")" = "rebase" ]
  [ "$(jq -r '.autoSaveInterval' "${data}")" = "10" ]
  [ "$(jq -r 'index("obsidian-git") != null' "${HOME}/Vault/.obsidian/community-plugins.json")" = "true" ]
}

@test "obsidian-sync: vault .gitignore excludes workspace + trash" {
  _run_sync
  gi="${HOME}/Vault/.gitignore"
  grep -q '.obsidian/workspace\*.json' "${gi}"
  grep -q '.trash/' "${gi}"
}

# ===== US4: systemd --user backstop + shell env =====
@test "obsidian-sync: installs + enables the daily push timer + linger" {
  _run_sync
  ud="${HOME}/.config/systemd/user"
  grep -q 'OnCalendar=daily' "${ud}/devboost-vault-sync.timer"
  grep -q 'Persistent=true' "${ud}/devboost-vault-sync.timer"
  grep -q 'pull --rebase --autostash' "${ud}/devboost-vault-sync.service"
  grep -q 'enable --now devboost-vault-sync.timer' "${STUB_SYSTEMCTL_LOG}"
  grep -q 'enable-linger' "${STUB_LOGINCTL_LOG}"
}

@test "obsidian-sync: exports VAULT_DIR via an idempotent bashrc block" {
  _run_sync; _run_sync
  [ "$(grep -c '# BEGIN devboost-vault-env' "${HOME}/.bashrc")" -eq 1 ]
  grep -q 'export VAULT_DIR=' "${HOME}/.bashrc"
}

# ===== verify + idempotency + OS gating =====
@test "obsidian-sync: verify RED before install, GREEN after" {
  run _run_verify
  [ "$status" -ne 0 ]
  _run_sync
  run _run_verify
  [ "$status" -eq 0 ]
}

@test "obsidian-sync: idempotent — second run succeeds, no duplicate units/keys" {
  _run_sync
  run _run_sync
  [ "$status" -eq 0 ]
  [ "$(grep -c '^Host notes-vault.github.com' "${HOME}/.ssh/config")" -eq 1 ]
}

@test "obsidian-sync: unsupported-OS — no install command on non-fedora" {
  run _module_install_cmd obsidian-sync ubuntu debian
  [ -z "$output" ]
}

@test "obsidian-sync: module metadata — category apps, requires obsidian+secrets+ssh-setup" {
  grep -q 'category    = "apps"' "${DEVBOOST_ROOT}/modules/obsidian-sync/module.toml"
  grep -q 'requires    = \["obsidian", "secrets", "ssh-setup"\]' "${DEVBOOST_ROOT}/modules/obsidian-sync/module.toml"
}
