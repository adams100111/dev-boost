# Tasks: secrets-and-auth

**Input**: Design documents from `specs/001-secrets-and-auth/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V (Test-First, NON-NEGOTIABLE) and spec SC-007. Every
behavior is specified by a failing bats test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). Shared library + test harness
are Foundational (blocking). Paths are repo-root relative per plan.md.

## Format: `[ID] [P?] [Story?] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1/US2/US3 (user-story phases only)

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Create the `modules/` directory and `tests/fixtures/secrets/` fixtures dir, with a sample decrypted bundle `tests/fixtures/secrets/bundle.json` (`{GIT_USER,GIT_EMAIL,GITHUB_PAT}`) and a short `tests/fixtures/secrets/README.md` describing the stubs.
- [ ] T002 [P] Harden `.gitignore` to exclude secret/key artifacts: `*.age`, age identity files (`age-key.txt`), `.git-credentials`, `id_ed25519*` (constitution §III; FR-012).

**Checkpoint**: repo scaffold + secret-hygiene ignore rules in place.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Both modules and the doctor preflight depend on `lib/secrets.sh` and the stub harness — complete this phase first.**

- [ ] T003 Write the shared bats stub harness `tests/fixtures/secrets/stubs.bash`: helpers to prepend PATH stub bins for `age` (emits the fixture JSON), `curl` (canned `GET`/`POST` responses keyed by URL + appends every invocation to a call-log file), and `ssh-keygen` (writes deterministic fake `id_ed25519{,.pub}`); plus scratch `HOME`/`XDG_STATE_HOME` setup and `DEVBOOST_SECRETS*` wiring. Used by all story tests.
- [ ] T004 Write `tests/secrets.bats` covering the `lib/secrets.sh` core (RED): `secrets_bundle_path` precedence; `secrets_decrypt` happy path + missing-bundle (exit 2) + cannot-decrypt (exit 3) + invalid-JSON (exit 4); `secrets_get`/wrappers + missing-field (exit 5); `have`/`ensure_pkg` (installs only when absent). Assert no PAT appears in any logged line.
- [ ] T005 Implement `lib/secrets.sh` (source-only) to pass T004: `secrets_bundle_path`, `secrets_decrypt`, `secrets_get`, `secrets_user/email/pat`, `have`, `ensure_pkg` — per `contracts/lib-secrets.md`. (`secrets_doctor` is added in US3.)

**Checkpoint**: decrypt/credential-read core is green; stories can begin.

---

## Phase 3: User Story 1 — Credentials available unattended (Priority: P1) 🎯 MVP

**Goal**: decrypt the bundle and configure git identity + HTTPS credentials with no prompt.
**Independent test**: with fixture bundle + stub `age`/`git`, run `modules/secrets/install.sh` under a scratch HOME → assert `.gitconfig`, `.git-credentials` (mode 600, github.com line), idempotent re-run skip, missing-field failure. No network.

- [ ] T006 [US1] Add `modules/secrets` install-behavior tests to `tests/secrets.bats` (RED): decrypt→`git config` identity→`credential.helper store`→`~/.git-credentials` written `600` with a single github.com line (no duplicate on re-run); missing required field → fail naming it (FR-003); PAT never echoed (FR-012); verify string green only when identity+credentials present.
- [ ] T007 [P] [US1] Create `modules/secrets/module.toml` per `contracts/module-secrets.md` (name, `requires=[]`, top-level `verify`, `[install].default` → `install.sh`).
- [ ] T008 [US1] Implement `modules/secrets/install.sh` to pass T006 per `contracts/module-secrets.md`: `ensure_pkg age` (per-OS), `secrets_decrypt`, extract fields, set git identity, seed credential store, `chmod 600`, replace-not-append the github.com line.
- [ ] T009 [US1] Add an idempotency + resolution test: running `bin/devboost install` with `DEVBOOST_MODULES_DIR=modules` and `DEVBOOST_PROFILES=tests/fixtures/secrets/profiles.toml` for the explicit module token `secrets` (not a `--profile`, which doesn't exist yet) reports installed first run, **skip** second run (engine verify-guard), proving end-to-end wiring (FR-009, SC-004). Add a minimal `tests/fixtures/secrets/profiles.toml` (empty `[profiles]`) so `profile_expand` resolves bare module tokens without a missing-file error.

**Checkpoint**: US1 independently demonstrable — MVP credential foundation works.

---

## Phase 4: User Story 2 — SSH key registered with GitHub (Priority: P2)

**Goal**: generate ed25519 (if absent) and register it via the API under `devboost:<hostname>`, non-blocking, idempotent.
**Independent test**: with stub `ssh-keygen`/`curl` (and stubbed `secrets_pat`), run `modules/ssh-setup/install.sh` → assert one `POST /user/keys` on first run, none when already registered (title or body), warn+continue on HTTP failure, hardened `~/.ssh/config` block, marker file written only on success.

- [ ] T010 [P] [US2] Write `tests/github.bats` (RED): `gh_api` sends the auth/Accept/version headers; `gh_upload_ssh_key` POSTs once on new key, skips when title matches, skips when key body matches, returns non-zero on HTTP error; `gh_add_deploy_key` POSTs with `read_only`; PAT never appears in the curl call-log or logs (FR-006, FR-013).
- [ ] T011 [US2] Implement `lib/github.sh` (source-only) to pass T010 per `contracts/lib-github.md`.
- [ ] T012 [P] [US2] Write `tests/ssh-setup.bats` (RED): keygen only when absent + never overwrites (FR-005); `~/.ssh` `700`/key `600`; hardened idempotent marker-delimited `~/.ssh/config` block; success→state marker written; upload-failure→`log_warn`, return 0, **no** marker (so engine verify-after-install handles strict/non-strict, FR-007); no PAT/privkey echoed.
- [ ] T013 [P] [US2] Create `modules/ssh-setup/module.toml` per `contracts/module-ssh-setup.md` (`requires=["secrets"]`, marker-based `verify`).
- [ ] T014 [US2] Implement `modules/ssh-setup/install.sh` to pass T012 per `contracts/module-ssh-setup.md` (uses `lib/github.sh` + `secrets_pat`).

**Checkpoint**: US2 independently demonstrable — machine self-registers its SSH key.

---

## Phase 5: User Story 3 — Preflight & secret safety (Priority: P3)

**Goal**: `doctor` reports secret readiness (4 states); the entrypoint guarantees `age`; no secret is ever tracked or world-readable.
**Independent test**: run `bin/devboost doctor` across present/absent/bad-key/age-missing fixtures → correct status + exit codes; `git ls-files` shows no secret/key/credential.

- [ ] T015 [US3] Write `tests/doctor.bats` (RED) per `contracts/doctor-preflight.md`: ready (exit 0), bundle-absent (warn, not a hard-fail by itself), cannot-decrypt (exit ≠0), age-missing (exit ≠0).
- [ ] T016 [US3] Add `secrets_doctor` (4-state: `ok`/`missing`/`cannot-decrypt`/`incomplete`) to `lib/secrets.sh` with covering cases in `tests/secrets.bats` (FR-010).
- [ ] T017 [US3] Implement the `cmd_doctor` additions in `bin/devboost` (age presence + `secrets_doctor` delegation) to pass T015 — read-only report, hard-fail only on age-missing/cannot-decrypt/incomplete.
- [ ] T018 [P] [US3] Extend the `install.sh` entrypoint preflight to guarantee `age` (per-OS, same commands as `modules/secrets`) alongside python3/jq, before any module runs (design §2).
- [ ] T019 [P] [US3] Add a hygiene test (`tests/doctor.bats` or `tests/hygiene.bats`) asserting `git ls-files` matches none of `*.age`, `id_ed25519*`, `*.git-credentials`, age identity files (SC-005, FR-012).

**Checkpoint**: US3 independently demonstrable — diagnosable + provably leak-free.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T020 Run the full suite `bats tests/` and confirm all green with **no regression** to the existing 36 engine-core tests.
- [ ] T021 [P] Reconcile `quickstart.md` commands against the final interfaces (fix any drift) and confirm the manual smoke block is accurate.
- [ ] T022 [P] Update `docs/roadmap.md` Spec 1 row status (⬜→✅) and note the delivered modules/libs (done at branch completion).

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T005)** → **US1 (T006–T009)** → **US2 (T010–T014)** → **US3 (T015–T019)** → **Polish (T020–T022)**.
- US1 is the MVP and depends only on Foundational. US2 depends on Foundational (`secrets_pat`) and is independently testable with a stubbed PAT source. US3 depends on Foundational (`lib/secrets.sh`) and reuses fixtures.
- TDD ordering inside each story: write RED test task → implement to GREEN.

## Parallel Opportunities
- T001 ∥ T002 (different files).
- T010 (github test) ∥ T012 (ssh-setup test) ∥ T013 (ssh-setup manifest) — different files; implement T011 before T014.
- T018 ∥ T019 (entrypoint vs hygiene test) within US3.
- Note: tasks touching the same file are NOT parallel — `tests/secrets.bats` is edited by T004, T006, T016 sequentially; `lib/secrets.sh` by T005 then T016.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): unattended credential foundation — independently shippable.
- Then US2 (SSH registration), then US3 (preflight/safety), each a green increment.
- Whole-branch review + `finishing-a-development-branch` after Polish.

**Total: 22 tasks** — Setup 2, Foundational 3, US1 4, US2 5, US3 5, Polish 3.
