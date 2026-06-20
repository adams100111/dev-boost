# Contract: Obsidian vault registration + Git-plugin seed (`obsidian-sync`, US2/US3)

## Vault registration (FR-010, US2)
`vault_obsidian_register` jq-merges a vault entry into Obsidian's config, preserving existing vaults:
- Flatpak (ALWAYS — default install): `~/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json`
- Native (ONLY if `~/.config/obsidian/` exists): `~/.config/obsidian/obsidian.json`
- merged shape: `.vaults[<id>] = { path: "$HOME/Vault", ts: <ms>, open: true }`; create the file
  (and parent dirs) with `{ "vaults": { … } }` if absent; never clobber other vault entries.

## Git-plugin seed (FR-013/FR-014, US3) — context7-verified keys (research.md)
`vault_seed_git_plugin` (seed-if-absent; the vault's committed `.obsidian/` wins if present):
- `~/Vault/.obsidian/plugins/obsidian-git/data.json` = the verified key set:
  `autoPullOnBoot:true, autoBackupAfterFileChange:true, autoSaveInterval:10, autoPullInterval:10,
  pullBeforePush:true, syncMethod:"rebase", commitMessage:"vault backup: {{date}}",
  autoCommitMessage:"vault backup: {{date}}", commitDateFormat:"YYYY-MM-DD HH:mm:ss"`
- `~/Vault/.obsidian/community-plugins.json` = JSON array containing `"obsidian-git"` (add-if-missing).
- `vault_gitignore` (FR-015): ensure `.gitignore` lines `.obsidian/workspace*.json` and `.trash/`.

## Tests (`tests/obsidian-sync.bats`, stubbed; real jq)
- flatpak obsidian.json created with `~/Vault` open:true; pre-existing vault entry preserved on merge.
- native path written only when `~/.config/obsidian/` pre-exists; untouched otherwise.
- data.json seeded with the exact verified keys (assert `syncMethod==rebase`, `autoSaveInterval==10`,
  `autoPullOnBoot==true`); pre-existing data.json NOT overwritten (seed-if-absent).
- community-plugins.json contains `obsidian-git`; not duplicated on re-run.
- .gitignore contains both ignore lines; idempotent.
