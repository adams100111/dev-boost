# Obsidian ↔ GitHub vault sync (design §7.1)

Unattended, secure-by-default notes sync (the `apps` profile's `obsidian-sync` module + `lib/vault.sh`).

## Auth — repo-scoped deploy key (not the account key, not a PAT)
- Generate `~/.ssh/notes_vault_ed25519` (passphrase-less, unattended).
- Register it as a **write deploy key** on the `notes-vault` repo via the GitHub API (bootstrap PAT, once).
- Isolated `~/.ssh/config` alias `notes-vault.github.com` (`IdentitiesOnly yes`); remote
  `git@notes-vault.github.com:USER/notes-vault.git`. A lost laptop exposes only the notes repo.

## Vault
- Clone → `~/Vault`; register it open-on-launch in Obsidian's config (Flatpak path always; native if present).
- Pre-seed the **Obsidian Git** plugin (`vinzent03/obsidian-git`) `data.json`: auto-pull-on-boot,
  commit-and-sync on change, `autoSaveInterval: 10`, `syncMethod: rebase`, dated commit messages —
  seed-if-absent (never clobber committed settings). `.gitignore` excludes `.obsidian/workspace*.json` + `.trash/`.

## Daily backstop
`devboost-vault-sync.{service,timer}` (`systemd --user`, `OnCalendar=daily`, `Persistent=true`):
add → commit → `pull --rebase --autostash` → push over the deploy key, logging to
`~/.local/state/devboost/vault-sync.log` — so a push happens even on days Obsidian never opens.
