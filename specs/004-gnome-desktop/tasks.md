# Tasks: gnome-desktop

**Input**: Design documents from `specs/004-gnome-desktop/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V + SC-007. Every module behavior is a failing bats
test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). `lib/gnome.sh` + stub-harness
extension + profile entries are Foundational. Paths repo-root relative.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create module folders under `modules/` for `gnome-settings`, `gnome-extensions`, `gnome-manager-apps`, `gnome-aesthetics`, `gnome-theme` (with `.gitkeep`).
- [ ] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — Specs 1–3 suite of 484 must stay green) with stubs for `gext` (records install by UUID; writes a fake `~/.local/share/gnome-shell/extensions/<UUID>/metadata.json` whose `uuid` = the requested UUID so author-verify passes; a knob to inject a MISMATCHED uuid for the failure test), `gnome-extensions`, `gnome-shell` (`--version` via `STUB_GNOME_SHELL_VERSION`), `dconf` (load records the dump path; a scratch dconf), `gsettings` (get/set an in-memory `enabled-extensions` list + interface keys, persisted to a scratch file), plus a `STUB_GNOME_PRESENT` knob (default 1). Run `bats tests/` → 484 still green.

**Checkpoint**: scaffold + extended GNOME harness ready.

---

## Phase 2: Foundational (Blocking)

- [ ] T003 Write `tests/gnome.bats` (RED) for `lib/gnome.sh` per `contracts/lib-gnome.md`: `gnome_require` (present→ok / `STUB_GNOME_PRESENT=0`→non-zero "unsupported"); `gnome_shell_version`; `ext_install` (skip-when-dir-present); `ext_verify_author` (mismatch→named fail); `ext_enable` (adds once, no dup on 2nd call); `dconf_load_managed`. Stubbed externals; assert real scratch state.
- [ ] T004 Implement `lib/gnome.sh` (source-only) to pass T003 per the contract (depends on `lib/log.sh`; reuse `have`/`need_cmd` from `lib/pkg.sh`).
- [ ] T005 Add `gnome`, `gnome-aesthetics`, `gnome-theme` entries to `profiles.toml` per `contracts/profiles.md`; extend `tests/profiles.bats` with `profile_expand` membership/count (TOML-only). Full `list --profile gnome` depsort test DEFERRED to T0XX (polish).

**Checkpoint**: shared GNOME helper + profiles resolve; stories can begin.

---

## Phase 3: User Story 1 — Desktop settings (Priority: P1) 🎯 MVP

**Goal**: reference look-and-feel applied via dconf, idempotent; unsupported on non-GNOME.
**Independent test**: settings module applies keys (stubbed gsettings/dconf) → reference values; re-run no-op; GNOME absent → unsupported failure.

- [ ] T006 [US1] Write `tests/gnome-settings.bats` (RED) per `contracts/gnome-settings.md`: apply → color-scheme/accent/scaling/button-layout/center-windows/tap-to-click set to reference; verify green; re-run idempotent; GNOME-absent → unsupported failure.
- [ ] T007 [US1] Create the dconf dump as a **repo data file** `modules/gnome-settings/gnome.dconf` (plain dconf INI, NOT a chezmoi `dot_` source) with the reference look-and-feel keys (NO secrets, **NO `enabled-extensions`** — that's owned by gnome-extensions) per the contract.
- [ ] T008 [US1] Implement `modules/gnome-settings/{module.toml,install.sh}` (`gnome_require`; `dconf_load_managed "$DEVBOOST_ROOT/modules/gnome-settings/gnome.dconf"`; verify a representative key). Pass T006.

**Checkpoint**: US1 MVP — desktop settings applied.

---

## Phase 4: User Story 2 — Functional extensions (Priority: P2)

**Goal**: the 6 functional extensions installed by pinned UUID + author-verified + enabled, session-free, idempotent.
**Independent test**: each UUID installed for detected version, author-verified, enabled once; mismatch→named fail; re-run no-dup; GNOME absent→unsupported.

- [ ] T009 [US2] Write `tests/gnome-extensions.bats` (RED) per `contracts/gnome-extensions.md`: each functional UUID `gext install` attempted for the detected shell version; author-verify passes for matching metadata and FAILS-named for an injected mismatch; each added once to `enabled-extensions` (assert count==1 per UUID after a double run); GNOME-absent → unsupported.
- [ ] T010 [US2] Implement `modules/gnome-extensions/{module.toml,install.sh}` (`requires=["gnome-settings"]`; `gnome_require`; ensure `gext`; for each pinned functional UUID: `ext_install`→`ext_verify_author`→`ext_enable`; verify all present+enabled). Reach GREEN for T009.

**Checkpoint**: US2 — functional extensions provisioned without a session.

---

## Phase 5: User Story 3 — Manager apps + opt-in bundles (Priority: P3)

**Goal**: manager/discovery/tweak apps; opt-in aesthetics + theme provisioned reproducibly.
**Independent test**: manager apps installed; aesthetics extensions installed+enabled (opt-in); theme provisioned (User Themes + vinceliuice tag + papirus/bibata/inter + dconf keys), no manual download; all idempotent.

- [ ] T011 [P] [US3] Write `tests/gnome-manager.bats` (RED) then implement `modules/gnome-manager-apps/{module.toml,install.sh}` (`requires=["gnome-settings"]`; official Extensions app + Extension Manager flatpak + gnome-tweaks, add-if-absent; verify presence). GREEN.
- [ ] T012 [P] [US3] Implement `modules/gnome-aesthetics/{module.toml,install.sh}` (OPT-IN; `requires=["gnome-settings"]`; install+enable the aesthetics UUID set via `lib/gnome.sh`, author-verify + enable-dedup; verify present+enabled) with its tests in `tests/gnome-manager.bats` or a section.
- [ ] T013 [US3] Write `tests/gnome-theme.bats` (RED) then implement `modules/gnome-theme/{module.toml,install.sh}` (OPT-IN; `requires=["gnome-settings"]`; User Themes ext+enable; pinned vinceliuice theme via `git clone` at a TAG + `./install.sh -l -c dark`; `papirus-icon-theme`+Bibata+`rsms-inter-fonts` via dnf + `fc-cache`; apply dconf theme keys; NO manual gnome-look.org; idempotent; verify theme/icon/cursor/font + User Themes enabled). GREEN.

**Checkpoint**: US3 — manager tooling + opt-in polish.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T014 Add the deferred full-resolution test to `tests/profiles.bats`: `devboost list --profile gnome` (real `profiles.toml` + all `modules/`) depsorts without cycle, `gnome-settings` before `gnome-extensions`/`gnome-manager-apps`. Then run the FULL suite `bats tests/` — all green, NO regression to Specs 1–3 (484) or engine.
- [ ] T015 [P] Reconcile `quickstart.md` against delivered module names/commands; fix any drift.
- [ ] T016 [P] Update `docs/roadmap.md` Spec 4 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003–T005) → US1 (T006–T008) → US2 (T009–T010) → US3 (T011–T013) → Polish (T014–T016).
- US1 is the MVP. US2 depends on US1 (the enabled-extensions key lives in the managed settings) and Foundational (`lib/gnome.sh`). US3 depends on US1 (theme applies via dconf keys).
- TDD inside each story: RED test → implement → GREEN.

## Parallel Opportunities
- T001 ∥ (T002 after); T011 ∥ T012 (different modules); T015 ∥ T016.
- Same-file tasks (profiles.bats edited by T005 + T014; stubs.bash by T002) are NOT parallel.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): desktop settings — independently shippable.
- Then US2 (functional extensions), US3 (manager + opt-in), each a green increment. Whole-branch review + finishing after Polish.

**Total: 16 tasks** — Setup 2, Foundational 3, US1 3, US2 2, US3 3, Polish 3.
