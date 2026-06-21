# Tasks: lifecycle-and-dev-hygiene

**Input**: Design documents from `specs/009-lifecycle-and-dev-hygiene/`

**Organization**: by user story (US1 add P1 → US6 aspire-gc P6). Engine-feature work, TDD (Principle V).
Paths repo-root relative. Single-file tasks (`bin/devboost`, `lib/lifecycle.sh`, `lib/devhygiene.sh`,
`tests/fixtures/base/stubs.bash`, `tests/profiles.bats`) are NOT parallel.

## Format: `[ID] [P?] [Story?] Description`

- TDD: each story = write the RED test first, then implement to GREEN.
- Constraint: existing `install`/`verify`/`list`/`doctor` behavior unchanged; keep the prior 935-test suite green (backward-compatible stubs only).

---

## Phase 1: Setup

- [X] T001 [P] Create `templates/module-skeleton/` and `config/` dirs; create `modules/aspire-gc/` dir.

## Phase 2: Foundational (Blocking)

- [X] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — 935 must stay green): `docker` (`ps`/`inspect`/`stats --no-stream`/`container prune`/`rm`/`stop` driven by knobs STUB_DOCKER_PS, STUB_DOCKER_INSPECT_PERSISTENT, STUB_DOCKER_INSPECT_PID, STUB_DOCKER_LOG), `ddev` extend with `poweroff`, `code` (`--list-extensions` → STUB_CODE_EXTS), `mise` extend with `ls`, `git` extend with `pull` (STUB_GIT_PULL_FAIL knob). Reuse dnf/flatpak/systemctl --user/loginctl/rpm. Add log+knob defaults + truncation. Run `bats tests/` → 935 still green.
- [X] T003 [P] Author `templates/module-skeleton/module.toml` (canonical fields with `__NAME__` placeholder) + `templates/module-skeleton/install.sh` (escape-hatch sourcing lib/log.sh+lib/pkg.sh).
- [X] T004 Add `dev-hygiene = ["aspire-gc"]` to `profiles.toml`; extend `tests/profiles.bats` with dev-hygiene membership (TOML-only). Depsort deferred to Polish.

**Checkpoint**: stubs + template + profile ready.

---

## Phase 3: US1 — `devboost add` (Priority: P1) 🎯 MVP

- [X] T005 [P] [US1] Write `tests/lifecycle.bats` (RED) US1 cases per contracts/lifecycle-verbs.md: `lc_add foo` creates valid modules/foo/module.toml from template (name=foo); refuses overwrite; rejects invalid name; `--folder` adds install.sh.
- [X] T006 [US1] Create `lib/lifecycle.sh` with `lc_add` (+ `lc_lock_path` stub) to GREEN; wire `cmd_add` into `bin/devboost` dispatch + usage. Existing verbs untouched.

**Checkpoint**: US1 MVP — one-command module scaffold.

---

## Phase 4: US2 — `devboost export` + `diff` (Priority: P2)

- [X] T007 [US2] Add US2 cases to `tests/lifecycle.bats` (RED): `lc_export` writes workstation-config/exports/<ts>/{dnf,flatpak,mise,vscode-extensions}.txt from stub outputs, gap-marker on missing tool, no mutation; `lc_diff` exit 0 in-sync, non-zero when a declared module verify fails (+names it).
- [X] T008 [US2] Implement `lc_export` + `lc_diff` in `lib/lifecycle.sh`; wire `cmd_export`/`cmd_diff` in `bin/devboost`. GREEN for T007.

**Checkpoint**: US2 — drift visibility (CI-usable diff).

---

## Phase 5: US3 — `devboost update` + `devboost.lock` (Priority: P3)

- [X] T009 [US3] Add US3 cases to `tests/lifecycle.bats` (RED) per contracts/devboost-lock.md: `lc_lock_write` produces sorted deterministic TSV (regenerate twice → identical), secret-free; `lc_update` seeds config/mise.toml if absent, writes proposals + regenerates lock, prints diff, and NEVER `git commit` (assert STUB_GIT_LOG has no commit).
- [X] T010 [US3] Implement `lc_lock_write` + `lc_update` in `lib/lifecycle.sh`; wire `cmd_update`; have `cmd_install` call `lc_lock_write` at end (regenerate lock). GREEN for T009.

**Checkpoint**: US3 — reproducible, review-gated updates.

---

## Phase 6: US4 — `devboost self-update` (Priority: P4)

- [X] T011 [US4] Add US4 cases to `tests/lifecycle.bats` (RED): `lc_self_update` runs `git -C $DEVBOOST_ROOT pull --ff-only` then re-validate; STUB_GIT_PULL_FAIL=1 → non-zero + named error.
- [X] T012 [US4] Implement `lc_self_update` in `lib/lifecycle.sh`; wire `cmd_self_update`. GREEN for T011.

**Checkpoint**: US4 — two-command propagation.

---

## Phase 7: US5 — `devboost dev status/gc/down` (Priority: P5)

- [X] T013 [P] [US5] Write `tests/devhygiene.bats` (RED) per contracts/dev-hygiene.md: `dh_status` warns on duplicate live AppHost; `dh_gc` removes a `persistent=false` + dead-PID container (`docker rm`), prunes exited, and does NOT remove persistent or live-PID containers; docker-absent → no-op success; `dh_down` invokes ddev poweroff + prune + gc.
- [X] T014 [US5] Create `lib/devhygiene.sh` (`dh_apphosts`, `dh_pid_alive`, `dh_status`, `dh_gc`, `dh_down`); wire `cmd_dev <status|gc|down>` in `bin/devboost`. GREEN for T013.

**Checkpoint**: US5 — precise resource hygiene.

---

## Phase 8: US6 — `aspire-gc` user timer module (Priority: P6)

- [X] T015 [P] [US6] Write `tests/aspire-gc.bats` (RED) per contracts/aspire-gc-units.md: install writes ~/.config/systemd/user/aspire-gc.{service,timer} (OnCalendar=hourly, Persistent=true, ExecStart `devboost dev gc`), `systemctl --user enable --now` + `loginctl enable-linger` invoked; idempotent; verify RED before / GREEN after; unsupported-OS → engine failure.
- [X] T016 [US6] Implement `modules/aspire-gc/{module.toml,install.sh,verify.sh}` (category=dev-hygiene, requires=["docker"], profiles=["dev-hygiene"], Fedora-only). GREEN for T015.

**Checkpoint**: US6 — automated hourly orphan reclaim.

---

## Phase 9: Polish & Cross-Cutting

- [X] T017 Add `tests/cli.bats` dispatch cases: `devboost help/usage` lists new verbs; unknown verb → usage+exit 1; existing install/verify/list/doctor still dispatch. Add dev-hygiene depsort to `tests/profiles.bats`. Run FULL `bats tests/` — green, NO regression to Specs 1–8 (935).
- [X] T018 [P] Generate the initial committed `devboost.lock` (run lock-write over resolved state) and reconcile quickstart/research against delivered libs/verbs.
- [X] T019 [P] Update `docs/roadmap.md` Spec 9 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001) → Foundational (T002–T004) → US1 (T005–T006) → US2 (T007–T008) → US3 (T009–T010) → US4 (T011–T012) → US5 (T013–T014) → US6 (T015–T016) → Polish (T017–T019).
- US1–US4 share `lib/lifecycle.sh` + `bin/devboost` + one `tests/lifecycle.bats` → sequential, incremental.
- US5 adds `lib/devhygiene.sh` (independent file) + `bin/devboost` dev dispatch.

## Parallel Opportunities
- T001/T003 (template) parallel. T013 (devhygiene test) and T015 (aspire-gc test) are independent files.
- T018 ∥ T019. Single-file tasks (bin/devboost, lib/lifecycle.sh, lib/devhygiene.sh, stubs.bash, profiles.bats) NOT parallel.

## Implementation Strategy
- **MVP = US1 add** (Phases 1–3): smallest engine-verb proof.
- Then US2…US6 incrementally; US5/US6 deliver the audit-found OOM fix. Whole-branch review + finish after Polish.

**Total: 19 tasks** — Setup 1, Foundational 3, US1 2, US2 2, US3 2, US4 2, US5 2, US6 2, Polish 3.
