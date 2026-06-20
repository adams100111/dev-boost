# Implementation Plan: apps-and-obsidian

**Branch**: `008-apps-and-obsidian` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-apps-and-obsidian/spec.md`

## Summary

Deliver the `apps` profile — six curated Flathub GUI apps (Obsidian, Bruno, Bitwarden, Flameshot,
LocalSend, VLC), one module each — plus `obsidian-sync`, an unattended Obsidian↔GitHub vault sync:
repo-scoped write **deploy key** + isolated SSH alias, clone → `~/Vault`, auto-open registration in
Obsidian (Flatpak + native), pre-seeded Obsidian Git plugin (live pull-on-open + commit-and-sync),
and a `systemd --user` daily-persistent push backstop. **Zero engine touch**: apps install via
`flatpak install -y flathub <id>` (existing precedent); `obsidian-sync` reuses `lib/github.sh`
(`gh_add_deploy_key`) + `lib/secrets.sh` and adds a feature-local `lib/vault.sh` (analogous to
`lib/fresh.sh`). All IDs/keys registry/context7-verified for 2026-06-21.

## Technical Context

**Language/Version**: Bash (`set -Eeuo pipefail`), same as engine; jq for JSON merges.
**Primary Dependencies**: flatpak + Flathub (base profile), git, ssh/ssh-keygen, systemd --user,
GitHub REST API (via `lib/github.sh`), `age`-decrypted secrets (via `lib/secrets.sh`).
**Storage**: filesystem only — `~/.ssh/*`, `~/Vault/**`, Obsidian config JSON, `~/.config/systemd/user/*`,
`~/.local/state/devboost/vault-sync.log`. No database.
**Testing**: bats; stub flatpak / ssh-keygen / ssh / git / systemctl --user / loginctl / GitHub-API curl;
real jq. No real network/flatpak/systemd.
**Target Platform**: Fedora workstation (reference OS); Fedora-only `[install]` keys.
**Project Type**: dev-boost data modules + feature-local lib helper (single project).
**Performance Goals**: N/A (install-time, unattended). **Constraints**: zero prompts; idempotent;
reproducible; no secrets in git; engine untouched. **Scale/Scope**: 7 modules + 1 lib + 1 profile entry.

## Constitution Check

*GATE: must pass before Phase 0 and re-checked after Phase 1.*

- **I. Engine + Data Separation** — PASS. No `bin/` or `lib/*.sh` engine-logic change. New code is
  data (modules) + a feature-local source-only helper `lib/vault.sh` (like `lib/fresh.sh` in Spec 6);
  reuses existing `lib/github.sh`/`lib/secrets.sh`. Each module declares `verify` + one `[install]` + `requires`.
- **II. Idempotent & Verify-Guarded** — PASS. Every step is skip-if-present / seed-if-absent /
  merge-not-clobber; each module has a verify; failures die NAMING the module + command.
- **III. Reproducible / repo is source of truth** — PASS. App IDs + plugin settings pinned in-repo
  (registry/context7-verified); secrets stay gitignored (`age`), never committed.
- **IV. Unattended** — PASS. No prompts; deploy key passphrase-less; deploy-key upload + clone use the
  pre-provisioned PAT/keys; systemd timer + linger arranged non-interactively.
- **V. Test-First (TDD)** — PASS. Each module/lib function is built test-first (RED→GREEN) with real
  assertions against stub logs / merged JSON.
- **VI. Cross-OS via Data** — PASS. Fedora-only `[install]`; non-Fedora → engine reports unsupported.

**Result: PASS (no deviations).** Re-checked post-Phase-1: still PASS — `lib/vault.sh` is feature
data-layer support, not engine; no engine file is modified.

## Project Structure

### Documentation (this feature)
```text
specs/008-apps-and-obsidian/
├── plan.md, spec.md, research.md, data-model.md, quickstart.md
├── checklists/requirements.md
└── contracts/{app-install,vault-provision,obsidian-config-and-plugin,vault-sync-units}.md
```

### Source Code (repository root)
```text
profiles.toml                      # + apps = [6 apps + obsidian-sync]
lib/vault.sh                       # NEW feature-local helper (source-only, stubbable)
modules/obsidian/        module.toml            # inline flatpak install + verify
modules/bruno/           module.toml
modules/bitwarden/       module.toml
modules/flameshot/       module.toml
modules/localsend/       module.toml
modules/vlc/             module.toml
modules/obsidian-sync/   module.toml + install.sh + verify.sh
tests/apps.bats                    # 6 app modules
tests/obsidian-sync.bats           # vault provision + config/plugin + systemd units
tests/vault.bats                   # lib/vault.sh unit tests (functions in isolation)
tests/fixtures/base/stubs.bash     # + flatpak/ssh-keygen/systemctl --user/loginctl stubs (backward-compatible)
tests/profiles.bats                # + apps membership + depsort
```

## Phase 0 — Research
See [research.md](./research.md): zero-engine-touch approach, 6 verified Flathub IDs (HTTP 200),
obsidian-git data.json keys (context7), deploy-key/ssh-alias/clone/obsidian-config/systemd design,
test stubbing plan. No open unknowns.

## Phase 1 — Design & Contracts
- [data-model.md](./data-model.md): profile entry, 7 modules, `lib/vault.sh` function set, asset shapes,
  FR traceability, depsort.
- contracts/: app-install, vault-provision (deploy key + ssh alias + clone), obsidian-config-and-plugin,
  vault-sync-units (systemd --user).
- [quickstart.md](./quickstart.md): how to validate the feature green, hermetically.
- Agent context: update the SPECKIT pointer in CLAUDE.md to this plan.

## Phase 2 — Tasks
`/speckit-tasks` generates `tasks.md` (Setup → Foundational `lib/vault.sh` + stubs + profile →
US1 apps → US2 vault provision → US3 config/plugin → US4 systemd backstop → Polish). NOT created here.
