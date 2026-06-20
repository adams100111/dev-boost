# Tasks: cli-and-shell

**Input**: Design documents from `specs/003-cli-and-shell/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V + SC-007. Every module behavior is a failing bats
test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). Stub-harness extension +
profile entries are Foundational. Paths repo-root relative. NOTE: `tests/cli.bats` is the
engine test — new tests use distinct names (`cli-tools.bats`, `shell.bats`, etc.).

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create module folders under `modules/` for the escape-hatch modules (`gh`, `tpm`, `claude-code`, `starship`, `ghostty`, `nerd-fonts`, `dotfiles`, `bash-config`).
- [ ] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — Spec 1/2 suites must stay green) with PATH stubs for `npm`, `cargo`, `fc-list`/`fc-cache`, `dnf copr` (COPR), and a `chezmoi apply` stub that records `--source`/`--destination` and simulates writing managed files into scratch `HOME`; knobs for font-present/absent and apply behavior. Run `bats tests/` to confirm 304 baseline still green.

**Checkpoint**: scaffold + extended harness ready.

---

## Phase 2: Foundational (Blocking)

- [ ] T003 Add the `cli` and `shell` entries to `profiles.toml` per `contracts/profiles.md` (do not touch `base`); extend `tests/profiles.bats` with `profile_expand cli`/`shell` membership/count tests (TOML-only; no modules needed yet). The full `list --profile cli,shell` depsort test is DEFERRED to Polish (T0XX) — modules don't all exist yet.

**Checkpoint**: profiles resolve; stories can begin.

---

## Phase 3: User Story 1 — Modern CLI toolset (Priority: P1) 🎯 MVP

**Goal**: all cli tools present + verifying; claude-code after mise; idempotent.
**Independent test**: run cli modules on the stub host → each verifies by binary; re-run no-op; unsupported-OS reported; claude-code orders after mise.

- [ ] T004 [P] [US1] Write `tests/cli-tools.bats` (RED) per `contracts/cli-tools.md`: representative tools' resolved fedora install + binary verify; idempotent skip; unsupported-OS failure; gh repo add-once; tpm clone-if-absent; claude-code orders after mise + npm-global install reached via `--force` (host-independent) + no token echo.
- [ ] T005 [US1] Create the 15 simple per-tool modules `modules/{eza,bat,btop,zoxide,atuin,direnv,delta,lazygit,lazydocker,dust,duf,sd,yq,tealdeer,fastfetch}.toml` (pure TOML; correct binary verifies — delta→`delta` pkg `git-delta`, tealdeer→`tldr`, dust→`dust` pkg `rust-dust`; per-OS keys). Pass the relevant T004 cases.
- [ ] T006 [P] [US1] Implement `modules/gh/{module.toml,install.sh}` (add GitHub CLI dnf repo if absent + install; verify `command -v gh`).
- [ ] T007 [P] [US1] Implement `modules/tpm/{module.toml,install.sh}` (git clone tpm to `~/.tmux/plugins/tpm` if absent; verify dir present; `requires=[]`).
- [ ] T008 [US1] Implement `modules/claude-code/{module.toml,install.sh}` (`requires=["mise"]`; **(F2)** ensure a node runtime via mise FIRST — `mise use -g node@lts` (or pinned LTS) if no node is available, since a fresh machine's mise has no node and `npm` would otherwise be missing — then `npm install -g @anthropic-ai/claude-code`; verify `command -v claude`; never echo a token). The test asserts the node-ensure step precedes the npm install in the call-log. Reach GREEN for T004.

**Checkpoint**: US1 MVP — modern toolset present.

---

## Phase 4: User Story 2 — Shell, prompt, terminal, fonts (Priority: P2)

**Goal**: starship installed, ghostty installed+configured, fonts installed; idempotent.
**Independent test**: run shell modules → starship/ghostty verify; copr added once; fonts via fc-list, skipped when present; unsupported-OS reported.

- [ ] T009 [P] [US2] Write `tests/shell.bats` + `tests/fonts.bats` (RED) per `contracts/shell-env.md`: starship install+verify; ghostty copr-enable-once + install + verify + unsupported-OS; nerd-fonts download+install when absent / SKIP when fc-list shows them + `fc-cache` run.
- [ ] T010 [P] [US2] Implement `modules/starship/{module.toml,install.sh}` (install binary; does NOT edit ~/.bashrc — init lives in the dotfiles rc).
- [ ] T011 [P] [US2] Implement `modules/ghostty/{module.toml,install.sh}` (`dnf copr enable -y scottames/ghostty` add-if-absent + install; Ptyxis left available).
- [ ] T012 [US2] Implement `modules/nerd-fonts/{module.toml,install.sh}` (download JetBrainsMono + Meslo Nerd Font Mono to `~/.local/share/fonts` if absent; `fc-cache -f`; verify via fc-list; pin URLs/versions; document Ptyxis Mono gotcha). Reach GREEN for T009.

**Checkpoint**: US2 — configured shell/terminal binaries + fonts.

---

## Phase 5: User Story 3 — Integrations + dotfiles apply (Priority: P3)

**Goal**: chezmoi source tree shipped; `dotfiles` applies configs idempotently; bash rc wires all init lines once.
**Independent test**: `chezmoi apply` (stubbed) writes managed files; re-apply → exactly one copy of each init line; verify green only after apply.

- [ ] T013 [US3] Organize dev-boost's `dotfiles/` into a chezmoi source per `contracts/dotfiles-apply.md`: `dot_bashrc` (curated rc + the starship/atuin/zoxide/fzf/direnv init lines + a `devboost` sentinel), `dot_tmux.conf`, `dot_config/starship.toml`, `dot_config/ghostty/config`, `dot_config/atuin/config.toml`, `private_dot_claude/` skeleton. NO secrets in any file. **(F1)** Importing the tmux/ghostty/bash configs from `/home/dev/repos/setup-scripts` (§6.1) is a **ONE-TIME COPY into the repo**, not a runtime/build dependency: copy from that path if it exists, else author dev-boost's own curated equivalent. Once copied, the files live in dev-boost's `dotfiles/` and the external repo is never referenced again (no CI/clean-clone dependency).
- [ ] T014 [US3] Write `tests/dotfiles.bats` (RED) per `contracts/dotfiles-apply.md`: `chezmoi apply --source $DEVBOOST_ROOT/dotfiles` (stubbed) writes `~/.bashrc`/`~/.config/starship.toml`/`~/.tmux.conf`; re-apply → EXACTLY ONE copy of each init line (assert count==1); verify green only after apply; the apply stub asserts `--source` points at the dev-boost tree.
- [ ] T015 [US3] Implement `modules/dotfiles/{module.toml,install.sh}` (`requires=["starship","atuin","zoxide","direnv"]`; `chezmoi apply --source "$DEVBOOST_ROOT/dotfiles" --destination "$HOME"`; verify representative managed file + sentinel) and `modules/bash-config/module.toml` (`requires=["dotfiles"]`; verify rc applied with init lines, single copy). Reach GREEN for T014.

**Checkpoint**: US3 — full shell wired together via chezmoi.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T016 Add the deferred full-resolution test to `tests/profiles.bats`: `devboost list --profile cli,shell` (real `profiles.toml` + all `modules/`) depsorts without cycle, `mise` before `claude-code`, inited tools before `dotfiles` before `bash-config`. Then run the FULL suite `bats tests/` — all green, NO regression to Spec 1/2 (304) or engine.
- [ ] T017 [P] Reconcile `quickstart.md` against delivered module names/commands; fix any drift.
- [ ] T018 [P] Update `docs/roadmap.md` Spec 3 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003) → US1 (T004–T008) → US2 (T009–T012) → US3 (T013–T015) → Polish (T016–T018).
- US1 is the MVP. US2 is independent of US1 (different tools) but tested after. US3 depends on US1/US2 tools existing (the rc inits them) and on chezmoi (base).
- TDD inside each story: RED test → implement → GREEN.

## Parallel Opportunities
- T001 ∥ (T002 after); within US1 T006 ∥ T007 (different modules) after T004; within US2 T010 ∥ T011 (different modules) after T009; T017 ∥ T018.
- Same-file tasks (profiles.bats edited by T003 + T016; stubs.bash by T002) are NOT parallel.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): modern toolset — independently shippable.
- Then US2 (shell/terminal/fonts), US3 (dotfiles wiring), each a green increment. Whole-branch review + finishing after Polish.

**Total: 18 tasks** — Setup 2, Foundational 1, US1 5, US2 4, US3 3, Polish 3.
