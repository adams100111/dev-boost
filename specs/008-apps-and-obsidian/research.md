# Phase 0 Research: apps-and-obsidian

All registry/version facts below were **verified on 2026-06-21**: Flathub app IDs against the
Flathub appstream API (`https://flathub.org/api/v2/appstream/<id>` → HTTP 200) and the Obsidian
Git plugin settings against context7 `/vinzent03/obsidian-git`. These IDs/keys ARE the in-repo
source of truth (Principle III).

## Cross-cutting decisions

- **D0. Zero engine touch (Principle I).** No change to `bin/` or `lib/*.sh` engine logic. GUI apps
  install via `flatpak install -y flathub <id>` directly in each module (precedent:
  `modules/gnome-manager-apps/install.sh`). `obsidian-sync` REUSES existing libraries — `lib/github.sh`
  (`gh_add_deploy_key`) and `lib/secrets.sh` (`secrets_pat`/`secrets_user`) from Spec 1 — and adds a
  new **feature-local** helper `lib/vault.sh` (data-layer support, analogous to `lib/fresh.sh` in
  Spec 6: source-only, PATH-stubbable, no engine coupling).
- **D1. One app = one module** (`category="apps"`, `profiles=["apps"]`, Fedora-only `[install]`,
  verify `flatpak info <id>`), so adding an app is one file and a non-Fedora OS reports unsupported
  by data (Principle VI).
- **D2. Deploy-key isolation (best practice, design §7.1).** A dedicated repo-scoped, passphrase-less
  ed25519 key registered as a **write** deploy key; an isolated `~/.ssh/config` host alias
  (`IdentitiesOnly yes`) so the vault remote uses only that key. A leaked laptop exposes only the
  notes repo (SC-005).
- **D3. Seed-if-absent everywhere.** The vault's committed `.obsidian/` travels with the repo; the
  module only seeds plugin settings / config when absent and never clobbers user-committed state
  (Principle II idempotency; FR-013/FR-014).

## Flathub app IDs (US1) — verified HTTP 200 on 2026-06-21

| App | Flathub app ID | verify |
|---|---|---|
| Obsidian | `md.obsidian.Obsidian` | `flatpak info md.obsidian.Obsidian` |
| Bruno | `com.usebruno.Bruno` | `flatpak info com.usebruno.Bruno` |
| Bitwarden | `com.bitwarden.desktop` | `flatpak info com.bitwarden.desktop` |
| Flameshot | `org.flameshot.Flameshot` | `flatpak info org.flameshot.Flameshot` |
| LocalSend | `org.localsend.localsend_app` | `flatpak info org.localsend.localsend_app` |
| VLC | `org.videolan.VLC` | `flatpak info org.videolan.VLC` |

**dbgate / DBeaver:** NOT a Flatpak in this profile. dbgate is the persistent container shipped by
the Spec 7 `data` stack (`templates/data/compose.yaml`); DBeaver is a documented optional alternative.
(Resolves the roadmap row's stale `dbgate` entry — design doc supersedes.)

## Obsidian Git plugin (US3) — context7-verified keys (`/vinzent03/obsidian-git`)

Plugin id `obsidian-git` (repo `vinzent03/obsidian-git`). Seed `~/Vault/.obsidian/plugins/obsidian-git/data.json`
(seed-if-absent) and enable in `~/Vault/.obsidian/community-plugins.json`. Verified default-settings keys:

| key | value to seed | verified semantics |
|---|---|---|
| `autoPullOnBoot` | `true` | pull on Obsidian launch |
| `autoBackupAfterFileChange` | `true` | debounced commit-and-sync on file modify/create/delete/rename |
| `autoSaveInterval` | `10` | commit-and-sync every N minutes (0 = disabled) |
| `autoPullInterval` | `10` | pull every N minutes (0 = disabled) |
| `pullBeforePush` | `true` | (this is the plugin default) |
| `syncMethod` | `"rebase"` | valid ∈ `merge`\|`rebase`\|`reset` — rebase = linear single-user history |
| `commitMessage` | `"vault backup: {{date}}"` | manual-commit template |
| `autoCommitMessage` | `"vault backup: {{date}}"` | auto-commit template |
| `commitDateFormat` | `"YYYY-MM-DD HH:mm:ss"` | date format |

No drift from the design doc §7.1 — all keys are current.

## Vault sync (US2/US4) — reused + new

- **Deploy key registration:** `gh_add_deploy_key <owner> <repo> <pubkey_file> <title>` (lib/github.sh,
  Spec 1) — defaults to **write** (no `--read-only`), idempotent (dedups by title + key body). Title
  e.g. `devboost-vault:$(hostname)`. PAT via `secrets_pat`.
- **SSH alias** (design §7.1): `Host notes-vault.github.com / HostName github.com / IdentityFile
  ~/.ssh/notes_vault_ed25519 / IdentitiesOnly yes`, written as a marker-delimited block (same
  technique as `ssh-setup`), separate from the account-wide block.
- **Remote:** `git@notes-vault.github.com:<user>/<repo>.git`; clone → `~/Vault` (seed-if-absent).
- **Repo identity:** `$DEVBOOST_VAULT_REPO` (default `notes-vault`), owner = `secrets_user`.
- **Obsidian vault registration:** Flatpak config
  `~/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json` (always, default install) + native
  `~/.config/obsidian/obsidian.json` (only if dir exists). jq-merge a vault entry with `open:true`
  preserving existing vaults (never clobber).
- **systemd --user backstop:** `devboost-vault-sync.service` (oneshot:
  `git -C ~/Vault add -A && git commit -m "vault backup: $(date -Is)" --quiet || true;
  git -C ~/Vault pull --rebase --autostash && git -C ~/Vault push`, log →
  `~/.local/state/devboost/vault-sync.log`) + `devboost-vault-sync.timer` (`OnCalendar=daily`,
  `Persistent=true`). Enable via `systemctl --user enable --now`; arrange linger so it runs without an
  active session (`loginctl enable-linger` — stubbed in tests).
- **Shell + XDG:** export `VAULT_DIR=$HOME/Vault` via the managed bash config and register an XDG user
  dir; `.gitignore` excludes `.obsidian/workspace*.json` and `.trash/`.

## Testing (no real network / flatpak / systemd)

Extend `tests/fixtures/base/stubs.bash` (backward-compatible) with stubs for: `flatpak` (`install`/`info`
+ presence knob), `ssh-keygen` (creates fake key/pub), `loginctl`, and `systemctl --user`
(enable/--now logging). Reuse existing `git`, `curl`, `jq` (real), and the Spec 1 GitHub-API curl stub.
Per-module bats assert: install command attempted with the right app ID/pin; verify GREEN; idempotent
re-run no-op; unsupported-OS → engine failure; deploy-key registered write (assert API payload);
ssh alias + clone over alias; obsidian config vault registered (both paths); plugin data.json seeded +
enabled (seed-if-absent preserves user settings); systemd units written + enabled. No real
installs/network/containers/systemd.

## Outcome

No unresolved NEEDS CLARIFICATION (all self-resolved + registry/context7-verified in spec §Clarifications).
Ready for Phase 1.
