# Tasks: editors

**Input**: Design documents from `specs/006-editors/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V + SC-007. Every module/helper behavior is a failing
bats test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). Stub-harness extension +
profile entry are Foundational. Paths repo-root relative.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create module folders under `modules/` for `vscode`, `fresh`, `fresh-lsp` (with `.gitkeep`).
- [ ] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — Specs 1–5 suite of 713 must stay green) with: a `code` stub (`--list-extensions` emits the `STUB_CODE_EXTENSIONS` set; `--install-extension <id>` appends to that set + records to a call log), a `mise` stub (`use -g <spec>` records to a log + marks the tool installed via `STUB_MISE_TOOLS`; `which <bin>` prints a deterministic fake absolute path or fails if uninstalled), and a `fresh`-install stub driving `curl`/`rpm -U`/`cargo` outcomes via `STUB_FRESH_INSTALL_VIA` (`rpm`/`script`/`cargo`/`none`) with `command -v fresh` honouring it. Reuse the existing `dnf`/`rpm`/file stubs for the MS `vscode.repo` write. Run `bats tests/` → 713 still green.

**Checkpoint**: scaffold + extended editors harness ready.

---

## Phase 2: Foundational (Blocking)

- [ ] T003 Add the `editors` entry to `profiles.toml` per `contracts/profiles.md` (`editors = ["vscode","fresh","fresh-lsp"]`; do NOT touch base/cli/shell/gnome/multimedia); extend `tests/profiles.bats` with `profile_expand editors` membership/count (3 modules, TOML-only). Full `list --profile editors` depsort test DEFERRED to Polish.

**Checkpoint**: profile resolves; stories can begin.

---

## Phase 3: User Story 1 — VS Code ready with curated extensions (Priority: P1) 🎯 MVP

**Goal**: VS Code installed from the MS repo with the curated baseline extensions, only-missing, idempotent; unsupported on non-Fedora.
**Independent test**: MS repo written + `code` installed + each baseline extension installed (only the missing ones); re-run no-op; non-Fedora → unsupported.

- [ ] T004 [P] [US1] Write `tests/vscode.bats` (RED) per `contracts/vscode.md`: MS `vscode.repo` written (idempotent, no dup on re-run); `dnf install -y code` attempted; for a partial `STUB_CODE_EXTENSIONS` only the MISSING `extensions.txt` IDs are installed via `code --install-extension` (present ones untouched); verify GREEN when `code` present AND all baseline extensions listed; idempotent skip; unsupported-OS (non-fedora `OS_DISTRO`) → engine failure.
- [ ] T005 [US1] Implement `modules/vscode/{module.toml,install.sh,extensions.txt}` (`requires=[]`; import MS key + write `/etc/yum.repos.d/vscode.repo` idempotently; `dnf install -y code`; install only-missing baseline extensions via `code --install-extension --force` as the invoking user; `verify` = `command -v code` AND every `extensions.txt` ID in `code --list-extensions`). Reach GREEN for T004.

**Checkpoint**: US1 MVP — VS Code ready with curated extensions.

---

## Phase 4: User Story 2 — `fresh` terminal editor ready (Priority: P2)

**Goal**: `fresh` installed on PATH via the rpm→script→cargo fallback chain; named failure if all fail; idempotent; unsupported on non-Fedora.
**Independent test**: each install channel exercised; all-fail→named die; re-run no-op; non-Fedora → unsupported.

- [ ] T006 [US2] Write `tests/fresh.bats` (RED) per `contracts/fresh.md`: `STUB_FRESH_INSTALL_VIA=rpm` → GitHub-release `.rpm` fetched + `rpm -U` attempted, verify GREEN; `=script` → script path attempted; `=cargo` → `cargo install --locked fresh-editor` attempted; `=none` → module FAILS naming `fresh` + the command; idempotent skip when `fresh` present; unsupported-OS → engine failure.
- [ ] T007 [US2] Implement `modules/fresh/{module.toml,install.sh}` (`requires=[]`; ordered install: GitHub-release `.rpm` via `curl`+`rpm -U` → official `install.sh` → `cargo install --locked fresh-editor`, re-checking `command -v fresh` after each, `die` naming `fresh` if all fail; `verify` = `command -v fresh`). Reach GREEN for T006.

**Checkpoint**: US2 — `fresh` terminal editor on PATH.

---

## Phase 5: User Story 3 — Profile-scoped language intelligence in `fresh`, mise-sourced (Priority: P3)

**Goal**: `lib/fresh.sh` provisions a server as a mise-managed pinned tool + idempotently jq-merges its `lsp` entry into `~/.config/fresh/config.json` (preserving other keys); `fresh-lsp` applies the always-on base set; scoping is structural (no stack module ⇒ no stack server).
**Independent test**: base-config seed (no clobber); provision = `mise use -g` + `mise which` + `lsp` merge; non-`lsp` keys preserved; idempotent re-run; only base languages present; `fresh` missing → named fail; non-Fedora → unsupported.

- [ ] T008 [P] [US3] Write `tests/fresh-lsp.bats` (RED) per `contracts/fresh-lsp.md`: absent config → seeded from `config.base.json` (theme + `format_on_save`, empty `lsp`); seed never clobbers a pre-existing config with a custom key; `fresh_lsp_provision` does `mise use -g <spec>` + resolves `mise which` + writes `lsp.<lang>` (absolute command, `enabled:true`); merge preserves `theme`/`editor`/prior `lsp.*`; idempotent re-run → unchanged `config.json` (verify GREEN); only `servers.base.tsv` languages present (no stack language); `fresh` missing at provision → FAIL naming the editor; unsupported-OS → engine failure.
- [ ] T009 [US3] Implement `lib/fresh.sh` — `fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin> [args…]`: `mise use -g <backend:tool@pin>` (idempotent), `abs=$(mise which <fresh-command>)` (`die` naming the tool if unresolved), jq-merge `{lsp:{<lang>:{command:$abs,args:[…],enabled:true}}}` into `~/.config/fresh/config.json` preserving all other keys, idempotent. (Profile-helper lib pattern — `lib/secrets.sh`/`lib/gnome.sh`.)
- [ ] T010 [US3] Implement `modules/fresh-lsp/{module.toml,install.sh,config.base.json,servers.base.tsv}` (`requires=["fresh","mise"]`; seed `config.base.json`→`~/.config/fresh/config.json` only if absent; for each `servers.base.tsv` row call `fresh_lsp_provision`; record the base-set pins in `config/mise.toml`; `verify` = every base tool resolvable via `mise which` AND its `lsp.<lang>` entry present+enabled; `fresh` missing → `die` named). Reach GREEN for T008.

**Checkpoint**: US3 — `fresh` is language-aware for the always-on base set; mechanism ready for dev-stacks (Spec 7) to add per-stack rows.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T011 Add the deferred full-resolution test to `tests/profiles.bats`: `devboost list --profile editors` (real `profiles.toml` + all `modules/`) depsorts without cycle, with `mise` and `fresh` before `fresh-lsp`. Then run the FULL suite `bats tests/` — all green, NO regression to Specs 1–5 (713) or engine.
- [ ] T012 [P] Reconcile `quickstart.md` against delivered module names/commands/extension list; fix any drift.
- [ ] T013 [P] Update `docs/roadmap.md` Spec 6 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003) → US1 (T004–T005) → US2 (T006–T007) → US3 (T008–T010) → Polish (T011–T013).
- US1 (`vscode`) and US2 (`fresh`) are independent (different modules, both `requires=[]`). US3 depends on `fresh` existing (its `requires`) and on `lib/fresh.sh`; within US3, T010 depends on T009.
- TDD inside each story: RED test → implement → GREEN.

## Parallel Opportunities
- T004 ∥ T005? No — same story, test-first (T004 RED before T005). T008 (test) ∥ T009 (lib/fresh.sh — different file) is allowed; T010 follows T009.
- T012 ∥ T013.
- Same-file tasks (`profiles.bats` edited by T003 + T011; `stubs.bash` by T002) are NOT parallel.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): VS Code + curated extensions — independently shippable.
- Then US2 (`fresh`), US3 (`fresh-lsp` + `lib/fresh.sh` mechanism + base set), each a green
  increment. Whole-branch review + finishing after Polish. Per-stack server rows are a
  later (dev-stacks / Spec 7) consumption of `lib/fresh.sh`, not part of this branch.

**Total: 13 tasks** — Setup 2, Foundational 1, US1 2, US2 2, US3 3, Polish 3.
