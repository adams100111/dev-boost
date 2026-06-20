# Quickstart: validate apps-and-obsidian (hermetic)

All validation is offline/stubbed — no real flatpak, network, ssh, or systemd.

## Run the feature's tests (TDD gates)
```sh
cd /home/dev/repos/dev-boost
bats tests/vault.bats          # lib/vault.sh unit tests
bats tests/apps.bats           # 6 Flathub app modules
bats tests/obsidian-sync.bats  # deploy key + clone + obsidian config + plugin seed + systemd units
bats tests/profiles.bats       # apps membership + full depsort
```

## Profile resolution (no install)
```sh
for m in obsidian bruno bitwarden flameshot localsend vlc obsidian-sync; do echo "$m"; done
./bin/devboost list --profile apps    # resolves without cycle; obsidian-sync after obsidian/secrets/ssh-setup
```

## What "green" proves
- 6/6 apps install via `flatpak install -y flathub <verified-id>` and verify via `flatpak info` (SC-001);
  re-run is a no-op (SC-002); non-Fedora → unsupported.
- NO dbgate flatpak installed (it is the data-stack container); DBeaver not installed.
- `obsidian-sync`: dedicated `~/.ssh/notes_vault_ed25519` generated; registered as a **write** deploy key
  (`POST /repos/<owner>/<repo>/keys` `read_only:false`); isolated `notes-vault.github.com` ssh alias;
  clone → `~/Vault`; Obsidian config (Flatpak always, native if present) opens `~/Vault` (SC-003).
- Obsidian Git plugin `data.json` seeded with context7-verified keys (syncMethod rebase, autoSaveInterval 10,
  autoPullOnBoot) + enabled; user-committed settings never clobbered.
- `devboost-vault-sync.{service,timer}` written + enabled (daily, Persistent) → push even if Obsidian
  never opens (SC-004); only the repo-scoped key is ever used (SC-005).

## Full backward-compat gate
```sh
bats tests/   # entire suite green (prior 887 + new apps/obsidian-sync/vault/profile tests), 0 engine changes
```

Pins/IDs source of truth: [research.md](./research.md). Contracts: [contracts/](./contracts/).
