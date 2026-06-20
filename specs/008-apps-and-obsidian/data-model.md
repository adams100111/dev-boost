# Phase 1 Data Model: apps-and-obsidian

No database. "Data" = module manifests, the `apps` profile entry, the vault deploy-key + ssh-alias,
Obsidian config registrations, the Obsidian Git plugin seed files, and the systemd --user units.
All Fedora-only `[install]` keys (Principle VI).

## Profile entry (`profiles.toml`)

```toml
apps = ["obsidian","bruno","bitwarden","flameshot","localsend","vlc","obsidian-sync"]
```

- `obsidian-sync` depends (via `requires`) on `obsidian` + secrets/git, so it sorts after them.

## Modules

| module | category | requires | install (fedora) | verify |
|---|---|---|---|---|
| `obsidian` | apps | `["flatpak"]` | `flatpak install -y flathub md.obsidian.Obsidian` | `flatpak info md.obsidian.Obsidian` |
| `bruno` | apps | `["flatpak"]` | `flatpak install -y flathub com.usebruno.Bruno` | `flatpak info com.usebruno.Bruno` |
| `bitwarden` | apps | `["flatpak"]` | `flatpak install -y flathub com.bitwarden.desktop` | `flatpak info com.bitwarden.desktop` |
| `flameshot` | apps | `["flatpak"]` | `flatpak install -y flathub org.flameshot.Flameshot` | `flatpak info org.flameshot.Flameshot` |
| `localsend` | apps | `["flatpak"]` | `flatpak install -y flathub org.localsend.localsend_app` | `flatpak info org.localsend.localsend_app` |
| `vlc` | apps | `["flatpak"]` | `flatpak install -y flathub org.videolan.VLC` | `flatpak info org.videolan.VLC` |
| `obsidian-sync` | apps | `["obsidian","secrets","ssh-setup"]` | `bash modules/obsidian-sync/install.sh` | `bash modules/obsidian-sync/verify.sh` |

App modules are tiny: each is a `module.toml` with an inline `flatpak install`/`flatpak info` (no
install.sh needed — matches the simplest existing flatpak precedent) OR a 3-line install.sh; the plan
uses inline install + verify in `module.toml` for the six apps to keep "adding an app = one file".

## `lib/vault.sh` (NEW feature-local helper — source-only, PATH-stubbable; NOT engine)

| function | responsibility |
|---|---|
| `vault_keygen` | generate `~/.ssh/notes_vault_ed25519` (ed25519, `-N ""`) if absent; perms 600 |
| `vault_ssh_alias` | ensure marker-delimited `Host notes-vault.github.com` block in `~/.ssh/config` (IdentityFile + IdentitiesOnly) |
| `vault_register_deploy_key` | `gh_add_deploy_key <owner> <repo> <pub> "devboost-vault:$(hostname)"` (write; idempotent) |
| `vault_clone` | clone `git@notes-vault.github.com:<owner>/<repo>.git` → `~/Vault` if absent |
| `vault_obsidian_register` | jq-merge `~/Vault` (open:true) into Flatpak obsidian.json (always) + native (if dir exists), preserving existing vaults |
| `vault_seed_git_plugin` | seed `.obsidian/plugins/obsidian-git/data.json` (seed-if-absent) + enable in `community-plugins.json` |
| `vault_gitignore` | ensure `.gitignore` excludes `.obsidian/workspace*.json`, `.trash/` |
| `vault_systemd_units` | write `~/.config/systemd/user/devboost-vault-sync.{service,timer}` + `systemctl --user enable --now` + `loginctl enable-linger`; idempotent |
| `vault_shell_env` | export `VAULT_DIR=$HOME/Vault` via managed bash config + XDG user-dir registration |

## Config / asset shapes

| asset | content |
|---|---|
| `~/.ssh/config` alias block | `Host notes-vault.github.com` → HostName github.com, IdentityFile ~/.ssh/notes_vault_ed25519, IdentitiesOnly yes (marker-delimited, separate from account block) |
| Obsidian `obsidian.json` | `{ vaults: { <id>: { path: "$HOME/Vault", ts, open: true } } }` merged, existing entries preserved |
| `data.json` (obsidian-git) | the context7-verified key set (research.md) — seed-if-absent |
| `community-plugins.json` | JSON array including `"obsidian-git"` (seed-if-absent / add-if-missing) |
| `devboost-vault-sync.service` | oneshot: add -A && commit \|\| true; pull --rebase --autostash && push; log → ~/.local/state/devboost/vault-sync.log |
| `devboost-vault-sync.timer` | `OnCalendar=daily`, `Persistent=true`, WantedBy=timers.target |

## Requirement traceability (highlights)

| data fact | FR |
|---|---|
| apps profile = 6 apps + obsidian-sync | FR-001, FR-002 |
| inline flatpak install + verify per app | FR-003 |
| Fedora-only install keys | FR-004 |
| no dbgate flatpak (container instead) | FR-005 |
| dedicated deploy key + write registration | FR-006, FR-007 |
| isolated ssh alias | FR-008 |
| clone → ~/Vault | FR-009 |
| obsidian.json vault registration (flatpak+native) | FR-010 |
| VAULT_DIR + XDG dir | FR-011 |
| obsidian-sync requires obsidian+secrets, named fail | FR-012 |
| obsidian-git data.json seed + enable | FR-013, FR-014 |
| .gitignore hygiene | FR-015 |
| systemd --user service + daily persistent timer | FR-016 |
| unattended + reproducible | FR-017 |
| registry/context7-verified IDs/keys | FR-018 |
| backward-compatible stubs, suite green | FR-019 |

## Dependency ordering (depsort)

```
flatpak → {obsidian,bruno,bitwarden,flameshot,localsend,vlc}
secrets → ssh-setup
{obsidian, secrets, ssh-setup} → obsidian-sync
```
