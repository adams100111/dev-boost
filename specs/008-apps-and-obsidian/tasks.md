# Tasks: apps-and-obsidian

**Input**: Design documents from `specs/008-apps-and-obsidian/`

**Organization**: by user story (US1 apps P1 → US4 systemd backstop P4). `lib/vault.sh` helper +
stub-harness + profile/membership scaffolding are Setup/Foundational. Paths repo-root relative.
App IDs / plugin keys are registry/context7-verified (research.md) — the in-repo source of truth.

## Format: `[ID] [P?] [Story?] Description`

- **[P]** = independent file, parallelizable. Same-file tasks (`stubs.bash`, `profiles.bats`,
  `lib/vault.sh`, `modules/obsidian-sync/install.sh`) are NOT parallel.
- TDD: each user story = write the RED test first, then implement to GREEN.
- Constraint: ZERO engine touch; keep the prior 887-test suite green (backward-compatible stubs only).

---

## Phase 1: Setup

- [X] T001 [P] Create module folders under `modules/` for `obsidian`, `bruno`, `bitwarden`, `flameshot`, `localsend`, `vlc`, `obsidian-sync`.

## Phase 2: Foundational (Blocking)

- [X] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — prior 887 must stay green) with stubs: `flatpak` (`install`/`info` + STUB_FLATPAK_PRESENT knob for verify), `ssh-keygen` (creates fake `<f>`+`<f>.pub`), `systemctl` `--user` (enable/--now → STUB_SYSTEMCTL_LOG), `loginctl` (enable-linger log). Reuse existing `git`, `curl` (GitHub-API stub from Spec 1), `jq` (real), `flatpak` log (STUB_FLATPAK_LOG). Add knobs + `base_install_*` + `base_remove_*`. Run `bats tests/` → 887 still green.
- [X] T003 [P] Write `tests/vault.bats` (RED) for `lib/vault.sh` functions in isolation: `vault_keygen` (idempotent), `vault_ssh_alias` (marker block, IdentitiesOnly, idempotent), `vault_register_deploy_key` (write via gh_add_deploy_key, dedup), `vault_clone` (over alias, skip-if-present), `vault_obsidian_register` (jq-merge flatpak+native, preserve existing), `vault_seed_git_plugin` (seed-if-absent + enable), `vault_gitignore`, `vault_systemd_units` (units + enable + linger, idempotent), `vault_shell_env`.
- [X] T004 Implement `lib/vault.sh` (NEW feature-local helper; source-only; sources lib/log.sh; reuses lib/github.sh + lib/secrets.sh) to GREEN for T003. No engine file touched.
- [X] T005 Add the `apps` profile entry to `profiles.toml` per `contracts/`/`data-model.md` (`apps = ["obsidian","bruno","bitwarden","flameshot","localsend","vlc","obsidian-sync"]`); extend `tests/profiles.bats` with `apps` membership/count (TOML-only). Full depsort DEFERRED to Polish.

**Checkpoint**: helper + stubs + profile resolve; stories can begin.

---

## Phase 3: US1 — `apps` GUI suite (Priority: P1) 🎯 MVP

- [X] T006 [P] [US1] Write `tests/apps.bats` (RED) per `contracts/app-install.md`: each of the 6 modules runs `flatpak install -y flathub <verified-id>` (assert STUB_FLATPAK_LOG); verify GREEN via `flatpak info <id>`; idempotent skip when present; unsupported-OS → engine failure; assert NO dbgate flatpak install.
- [X] T007 [P] [US1] Implement `modules/obsidian/module.toml` (inline `flatpak install -y flathub md.obsidian.Obsidian`; verify `flatpak info md.obsidian.Obsidian`).
- [X] T008 [P] [US1] Implement `modules/bruno/module.toml` (com.usebruno.Bruno).
- [X] T009 [P] [US1] Implement `modules/bitwarden/module.toml` (com.bitwarden.desktop).
- [X] T010 [P] [US1] Implement `modules/flameshot/module.toml` (org.flameshot.Flameshot).
- [X] T011 [P] [US1] Implement `modules/localsend/module.toml` (org.localsend.localsend_app).
- [X] T012 [P] [US1] Implement `modules/vlc/module.toml` (org.videolan.VLC). Reach GREEN for T006.

**Checkpoint**: US1 MVP — GUI app suite installs + verifies.

---

## Phase 4: US2 — Vault provisioning (deploy key + ssh alias + clone) (Priority: P2)

- [X] T013 [US2] Write the US2 portion of `tests/obsidian-sync.bats` (RED) per `contracts/vault-provision.md`: dedicated key generated once; ssh alias block (IdentitiesOnly + dedicated IdentityFile) idempotent; deploy key registered WRITE (`POST /repos/<owner>/<repo>/keys` `read_only:false`, dedup); clone over the `notes-vault.github.com` alias → `~/Vault`; missing PAT → named die; unsupported-OS → engine failure.
- [X] T014 [US2] Implement `modules/obsidian-sync/module.toml` (`requires=["obsidian","secrets","ssh-setup"]`, category="apps", profiles=["apps"], Fedora-only install + verify.sh) and the US2 portion of `modules/obsidian-sync/install.sh` (source lib/log.sh+secrets.sh+github.sh+vault.sh; `secrets_pat` or die; `vault_keygen`/`vault_ssh_alias`/`vault_register_deploy_key`/`vault_clone`) + `modules/obsidian-sync/verify.sh` (key + alias + `~/Vault/.git`). GREEN for T013's US2 cases.

**Checkpoint**: US2 — vault present, registered over a repo-scoped key.

---

## Phase 5: US3 — Obsidian config + Git-plugin seed (Priority: P3)

- [X] T015 [US3] Add the US3 portion to `tests/obsidian-sync.bats` (RED) per `contracts/obsidian-config-and-plugin.md`: flatpak obsidian.json registers `~/Vault` open:true (pre-existing vault preserved); native path only if dir pre-exists; data.json seeded with verified keys (syncMethod rebase, autoSaveInterval 10, autoPullOnBoot true), pre-existing data.json not overwritten; community-plugins.json contains `obsidian-git` (no dup); .gitignore has both hygiene lines.
- [X] T016 [US3] Extend `modules/obsidian-sync/install.sh` with the US3 step (`vault_obsidian_register` + `vault_seed_git_plugin` + `vault_gitignore`) and `verify.sh` (obsidian.json has the vault; data.json present + plugin enabled). GREEN for T015.

**Checkpoint**: US3 — vault auto-opens + live sync configured.

---

## Phase 6: US4 — Daily push backstop (systemd --user) (Priority: P4)

- [X] T017 [US4] Add the US4 portion to `tests/obsidian-sync.bats` (RED) per `contracts/vault-sync-units.md`: both unit files written (OnCalendar=daily, Persistent=true, Type=oneshot, the add/commit/pull --rebase --autostash/push command, log path); `systemctl --user enable --now devboost-vault-sync.timer` + `loginctl enable-linger` invoked; idempotent re-run.
- [X] T018 [US4] Extend `modules/obsidian-sync/install.sh` with `vault_systemd_units` + `vault_shell_env` (VAULT_DIR + XDG dir) and `verify.sh` (units present + timer enabled). GREEN for T017.

**Checkpoint**: US4 — push happens even if Obsidian never opens.

---

## Phase 7: Polish & Cross-Cutting

- [X] T019 Add full-resolution depsort tests to `tests/profiles.bats` for `apps` (`devboost list --profile apps` resolves without cycle; obsidian-sync after obsidian/secrets/ssh-setup; flatpak before each app). Then run FULL `bats tests/` — all green, NO regression to Specs 1–7 (887) or engine.
- [X] T020 [P] Reconcile `quickstart.md` + `research.md` against delivered modules/IDs; fix any drift.
- [X] T021 [P] Update `docs/roadmap.md` Spec 8 row status (done at branch completion); note dbgate-is-container reconciliation.

---

## Dependencies & Execution Order
- Setup (T001) → Foundational (T002–T005) → US1 (T006–T012) → US2 (T013–T014) → US3 (T015–T016) → US4 (T017–T018) → Polish (T019–T021).
- US2/US3/US4 all live in `modules/obsidian-sync/{install.sh,verify.sh}` + one shared `tests/obsidian-sync.bats` → sequential (same files), built incrementally on `lib/vault.sh` (Foundational).
- All `*-lsp`-style reuse: obsidian-sync depends on editors-era libs? No — depends on Spec 1 secrets/ssh-setup + the obsidian app module. base/secrets on main.

## Parallel Opportunities
- US1 app modules T007–T012 are independent files (parallel); their test T006 is one file.
- T003 (tests/vault.bats) parallel with T001/T002 setup of unrelated files; but T004 depends on T002 stubs + T003.
- T020 ∥ T021. Same-file tasks (`stubs.bash` T002; `profiles.bats` T005+T019; `lib/vault.sh` T004; `obsidian-sync/install.sh` T014+T016+T018) are NOT parallel.

## Implementation Strategy
- **MVP = US1 apps** (Phases 1–3): the standalone GUI suite.
- Then US2→US4 build obsidian-sync incrementally on `lib/vault.sh`, each an independently-testable green increment.
- Whole-branch review + finishing after Polish.

**Total: 21 tasks** — Setup 1, Foundational 4, US1 7, US2 2, US3 2, US4 2, Polish 3.
