# Contract: vault provisioning — deploy key + SSH alias + clone (`obsidian-sync`, US2)

`obsidian-sync` module: `category="apps"`, `requires=["obsidian","secrets","ssh-setup"]`,
only `[install].fedora`, sources `lib/log.sh` + `lib/secrets.sh` + `lib/github.sh` + `lib/vault.sh`.

## install.sh (US2 portion)
1. `have obsidian flatpak`/prereqs; `pat="$(secrets_pat)"` — die NAMED if absent (FR-012).
2. `vault_keygen` → `~/.ssh/notes_vault_ed25519` (ed25519, `-N ""`), perms 600, skip-if-present (FR-006).
3. `vault_ssh_alias` → marker-delimited `Host notes-vault.github.com` block (IdentityFile +
   IdentitiesOnly), idempotent, separate from the account-wide block (FR-008).
4. `vault_register_deploy_key` → `gh_add_deploy_key "$(secrets_user)" "${DEVBOOST_VAULT_REPO:-notes-vault}"
   ~/.ssh/notes_vault_ed25519.pub "devboost-vault:$(hostname)"` — WRITE (no --read-only), idempotent (FR-007).
5. `vault_clone` → `git clone git@notes-vault.github.com:<owner>/<repo>.git ~/Vault` if `~/Vault` absent (FR-009).

## verify.sh (US2 portion)
- `~/.ssh/notes_vault_ed25519` exists AND `~/.ssh/config` contains the `notes-vault.github.com` alias
  AND `~/Vault/.git` exists.

## Tests (`tests/obsidian-sync.bats`, stubbed)
- ssh-keygen stub creates key+pub; assert key generated once (idempotent on re-run).
- assert ssh alias block written with IdentitiesOnly + the dedicated IdentityFile; re-run does not duplicate.
- GitHub API stub: assert a POST to `/repos/<owner>/<repo>/keys` with `read_only:false` (write); assert
  dedup (no second POST when already registered).
- git stub: assert clone over the `notes-vault.github.com` alias to `~/Vault`; skip when present.
- secrets absent (no PAT) → install dies NAMING the missing prerequisite (FR-012).
- unsupported-OS → engine failure. No real network/ssh/git.
