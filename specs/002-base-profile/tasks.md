# Tasks: base-profile

**Input**: Design documents from `specs/002-base-profile/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V (Test-First) + SC-007. Every module behavior is a
failing bats test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). Shared `lib/pkg.sh`,
`profiles.toml`, and the base stub harness are Foundational. Paths repo-root relative.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create the base module directory scaffold under `modules/` (folders for `rpmfusion`, `dnf-tune`, `fedora-third-party`, `flatpak`, `mise`, `chezmoi`, `docker`). (No `config/mise.toml` — per F2, install-time migration writes the USER global mise config, not the repo pin.)
- [ ] T002 [P] Create `tests/fixtures/base/stubs.bash`: PATH-stub harness for `dnf`, `rpm`, `flatpak`, `fedora-third-party`, `systemctl`, `usermod`, `getent`, `mise`, `chezmoi`, `git`, and `sudo` (sudo exec's the rest); each stub logs invocations and supports present/absent state knobs (env + fake `~/.nvm`/`~/.sdkman`, scratch `HOME`/`~/.bashrc`/`/etc/dnf/dnf.conf` roots). Reuse the Spec-1 stub pattern.

**Checkpoint**: scaffold + base stub harness ready.

---

## Phase 2: Foundational (Blocking)

**⚠️ `lib/pkg.sh`, `profiles.toml`, and the harness gate all stories.**

- [ ] T003 Write `tests/pkg.bats` (RED) for `lib/pkg.sh` per `contracts/lib-pkg.md`: `have`/`need_cmd`, `dnf_install`, `rpm_q`, `flatpak_remote_add` (skip-when-present), `write_kv_conf` (reconcile-not-duplicate + preserves other lines), `comment_block` (idempotent + preserves other lines), `mise_drift` (both/one/neither active). Stubbed externals; assert real file contents.
- [ ] T004 Implement `lib/pkg.sh` (source-only) to pass T003 per `contracts/lib-pkg.md`. Reconcile `have` with `lib/secrets.sh` (single canonical definition; source rather than redefine).
- [ ] T005 Create `profiles.toml` with the `base` set per `contracts/profiles.md`, and write `tests/profiles.bats` (RED→GREEN) for `profile_expand base` **membership/count only** (reads the TOML; needs no modules to exist). NOTE: the full `devboost list --profile base` depsort test is DEFERRED to T019 (Polish), because `depsort`→`module_file` dies on a not-yet-built module, so it can only pass once all base modules exist.

**Checkpoint**: shared helpers + profile resolve green; stories can begin.

---

## Phase 3: User Story 1 — Repos & package manager (Priority: P1) 🎯 MVP

**Goal**: extra repos + tuned dnf + third-party + full Flathub, idempotent, before any nonfree install.
**Independent test**: run the four modules on the stub host → repos/tuning/remote present, idempotent re-run, unsupported-OS reported.

- [ ] T006 [P] [US1] Write `tests/repos.bats` (RED) per `contracts/repos-and-pkgmgr.md` covering all four modules (rpmfusion release rpms + appstream + refresh; dnf-tune reconcile; fedora-third-party enable/query; flatpak flathub add + unfilter), idempotent re-run, and unsupported-OS.
- [ ] T007 [US1] Implement `modules/rpmfusion/{module.toml,install.sh}` (verify `rpm -q` both releases; install both release rpms + `dnf upgrade --refresh` + appstream-data).
- [ ] T008 [P] [US1] Implement `modules/dnf-tune/{module.toml,install.sh}` (`write_kv_conf` the two keys; verify both present).
- [ ] T009 [P] [US1] Implement `modules/fedora-third-party/{module.toml,install.sh}` (enable; verify via query).
- [ ] T010 [P] [US1] Implement `modules/flatpak/{module.toml,install.sh}` (install + `flatpak_remote_add flathub` + unfilter; verify remote present). Reach GREEN for T006.

**Checkpoint**: US1 MVP — package foundation present & idempotent.

---

## Phase 4: User Story 2 — Essential CLI + build tools (Priority: P2)

**Goal**: per-tool modules + build-tools bundle verify present; re-run no-op.
**Independent test**: each tool module resolves + verifies; build-tools installs the §10c set; unsupported-OS reported.

- [ ] T011 [P] [US2] Write `tests/tools.bats` (RED): for a representative subset + all-resolve check, assert each per-tool module's fedora install command and `command -v` verify, idempotent skip, and the unsupported-OS path.
- [ ] T012 [US2] Create the simple per-tool modules `modules/{coreutils,git,curl,wget,unzip,jq,htop,ripgrep,fd,fzf,tmux}.toml` per `contracts/cli-and-build-tools.md` (pure TOML; correct binary-name verifies: ripgrep→rg, etc.; per-OS keys). Pass T011.
- [ ] T013 [P] [US2] Write `tests/build-tools.bats` (RED) then implement `modules/build-tools/module.toml`: install the exact design §10c package list; verify key compilers (`gcc`/`make`/`cmake`). GREEN.

**Checkpoint**: US2 — shell + build toolchain present.

---

## Phase 5: User Story 3 — Runtime / dotfiles / container managers (Priority: P3)

**Goal**: mise (+migration), chezmoi (requires secrets), docker (service+group), doctor drift warning.
**Independent test**: migration present/absent branches; chezmoi clone non-blocking; docker group via getent + re-login reported; doctor warns only on drift.

- [ ] T014 [P] [US3] Write `tests/mise.bats` (RED) per `contracts/managers.md`: install; migration present-branch (fake `~/.nvm` version → `mise use -g node@v` writes the user global mise config, bashrc commented, version unchanged), absent-branch (no migration), empty-legacy edge; idempotent re-run. (Asserts the USER mise config, NOT the repo `config/mise.toml`.)
- [ ] T015 [US3] Implement `modules/mise/{module.toml,install.sh}` (install + conditional idempotent nvm/sdkman migration via `mise use -g` + `comment_block`; does NOT write repo `config/mise.toml`). Pass T014.
- [ ] T016 [P] [US3] Write `tests/chezmoi.bats` (RED) then implement `modules/chezmoi/{module.toml,install.sh}` (`requires=["secrets"]`; install + init + credentialed clone; clone-failure → warn + return 0; no credential echo; verify binary + chezmoi dir). GREEN.
- [ ] T017 [P] [US3] Write `tests/docker.bats` (RED) then implement `modules/docker/{module.toml,install.sh}` (repo add-if-absent + install + `systemctl enable --now` + `usermod -aG` only if absent; verify via `getent group docker`; report re-login). GREEN.
- [ ] T018 [US3] Write `tests/doctor-mise.bats` (RED) then add the `mise_drift` delegation to `bin/devboost::cmd_doctor` per `contracts/doctor-mise-drift.md` (warning, not hard-fail). GREEN. (Sanctioned engine touch — `cmd_doctor` only.)

**Checkpoint**: US3 — all three managers wired; drift diagnosable.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T019 Add the deferred full-resolution test to `tests/profiles.bats`: `devboost list --profile base` (real `profiles.toml` + all `modules/`) depsorts without cycle and orders `rpmfusion`/`secrets` before dependents. Then run the full suite `bats tests/` — all green, **no regression** to Spec 1 (118) or engine tests.
- [ ] T020 [P] Reconcile `quickstart.md` against the delivered module names/commands; fix any drift.
- [ ] T021 [P] Update `docs/roadmap.md` Spec 2 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003–T005) → US1 (T006–T010) → US2 (T011–T013) → US3 (T014–T018) → Polish (T019–T021).
- US1 is the MVP. US2 depends on US1's repos (dnf installs) but is independently testable with stubbed dnf. US3 depends on Foundational (`lib/pkg.sh`) and, for chezmoi, on Spec 1's `secrets` (on main).
- TDD inside each story: RED test → implement → GREEN.

## Parallel Opportunities
- T001 ∥ T002; within US1 T008 ∥ T009 ∥ T010 (different module files) after T006's test exists and T007 (rpmfusion ordering) is settled; T011 ∥ T013; T014 ∥ T016 ∥ T017 (different files).
- Same-file tasks are NOT parallel.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): package foundation — independently shippable.
- Then US2 (tools), US3 (managers), each a green increment. Whole-branch review + finishing after Polish.

**Total: 21 tasks** — Setup 2, Foundational 3, US1 5, US2 3, US3 5, Polish 3.
