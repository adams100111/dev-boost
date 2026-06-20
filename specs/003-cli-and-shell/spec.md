# Feature Specification: cli-and-shell

**Feature Branch**: `003-cli-and-shell`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "cli-and-shell — the modern CLI toolset + configured shell/terminal environment, restored from chezmoi-managed dotfiles (design §5, §6.1, §6.2; roadmap Spec 3)."

## Overview

This feature makes the terminal a first-class, productive environment. It installs the
modern command-line toolset (`cli` profile) and stands up the configured interactive
shell/terminal (`shell` profile): a default prompt, an opinionated shell config, the
primary terminal emulator, and the fonts they need — with all the opinionated
configuration applied from dev-boost's chezmoi-managed dotfiles so a freshly-built
machine looks and behaves exactly like the reference setup. It ships as self-contained
modules over the existing engine, reusing the escape-hatch, `lib/pkg.sh` helpers, and
bats stub-harness from Specs 1–2 (which provide `mise`, `chezmoi`, repos).

## Clarifications

### Session 2026-06-20 (self-answered from the design doc — source of truth; user autonomous)

- Q: Is chezmoi's source the dev-boost repo's `dotfiles/` tree or the user's `DEVBOOST_DOTFILES_REPO` clone? → A: This feature ships its curated configs in **dev-boost's own chezmoi source tree** (`dotfiles/` in the repo) and applies them with `chezmoi apply`; that is the source of truth for the shipped shell configs (design §2, §6.5). A user's personal `DEVBOOST_DOTFILES_REPO` (optional, from base) is a separate personal layer and is out of scope here.
- Q: Is the default prompt starship or oh-my-posh? → A: **starship** is the default and the only prompt in this feature; oh-my-posh remains a separate opt-in profile (design §6.2), out of scope here.
- Q: Granularity of the CLI tools? → A: one small module per tool (engine principle "adding a tool is one file"); only tools with real logic (e.g. claude-code via npm/mise, a tool needing a vendor repo) use an escape hatch.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Modern CLI toolset is present (Priority: P1)

After base, the operator has the full modern command-line toolset — better `ls`/`cat`/
`grep`/`du`/`df`/`cd`/history, git/docker TUIs, a JSON/YAML processor, the GitHub CLI,
tldr pages, a fetch tool, and the primary AI agent CLI — so day-one terminal work is
fast and ergonomic.

**Why this priority**: The tools are the foundation of the terminal experience and are
independently useful even before any config is applied. This is the MVP slice.

**Independent Test**: Run the `cli` tool modules on a fixture host and assert each named
tool verifies present; idempotent re-run is a no-op; the AI agent CLI (needing the
runtime manager) installs only after its prerequisite.

**Acceptance Scenarios**:

1. **Given** base is in place, **When** the cli modules run, **Then** each modern CLI tool verifies as installed (by its real binary name).
2. **Given** a tool that requires the runtime manager (the AI agent CLI), **When** the cli profile runs, **Then** that tool is installed only after its prerequisite is satisfied (dependency-ordered).
3. **Given** the tools are installed, **When** the modules run again, **Then** all report already-satisfied (idempotent).
4. **Given** a host lacking a tool's package on its OS, **When** the module runs, **Then** it is reported unsupported-on-this-OS (a failure), never silently skipped.

---

### User Story 2 - Shell, prompt, terminal, and fonts are configured (Priority: P2)

The operator's interactive shell shows the opinionated prompt, the terminal emulator
opens with the shipped theme/font, and the fonts the prompt and terminal need are
installed — all matching the reference experience, applied automatically.

**Why this priority**: Delivers the recognizable, productive environment, but depends on
the tools (US1) and the dotfiles mechanism being present.

**Independent Test**: Run the shell modules on a fixture host and assert: the prompt tool
is installed and initialized in the shell startup; the shell config is applied; the
terminal emulator is installed with its shipped config in place; the required fonts are
installed and detectable. Re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** the cli tools are present, **When** the shell modules run, **Then** the default prompt is installed and wired into the interactive shell startup, and the opinionated prompt configuration is in place.
2. **Given** the shell modules run, **When** complete, **Then** the curated shell configuration (aliases/functions/rc) is applied to the user's shell startup.
3. **Given** the shell modules run, **When** complete, **Then** the primary terminal emulator is installed with the shipped configuration (theme, font, keybinds) applied; the platform's fallback terminal is left available.
4. **Given** the shell modules run, **When** complete, **Then** the required developer fonts are installed and detectable by font tooling.
5. **Given** the shell environment is configured, **When** the modules run again, **Then** nothing changes (idempotent apply).

---

### User Story 3 - Shell integrations and multiplexer config are wired (Priority: P3)

The operator gets the productivity integrations — smart history, smart directory jumping,
fuzzy finding, per-directory environments — and the terminal multiplexer configured to
the reference setup, so the shell is not just installed but fully wired together.

**Why this priority**: Highest-polish layer; depends on the tools and shell config being
present first.

**Independent Test**: Run the integration modules on a fixture host and assert each
integration is initialized in the shell startup and the multiplexer config is applied;
re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** the tools and shell config are present, **When** the integration modules run, **Then** smart history, directory-jump, fuzzy-find, and per-directory-environment hooks are initialized in the shell startup.
2. **Given** the integration modules run, **When** complete, **Then** the terminal multiplexer configuration (imported verbatim from the reference) is applied.
3. **Given** the integrations are wired, **When** the modules run again, **Then** nothing changes (idempotent).

### Edge Cases

- A tool's binary name differs from its package name → verify uses the binary name (e.g. the better-ls/grep tools); unknown OS → reported unsupported.
- The AI agent CLI's runtime prerequisite is absent → dependency ordering installs it first; if the runtime is genuinely unavailable, the module fails naming the missing prerequisite (not silently).
- A shipped config file already exists on the machine (hand-edited) → the apply is idempotent and the managed content is reconciled without clobbering unrelated user content beyond the managed scope; re-apply is safe.
- The shell startup file already sources the prompt/integrations → not duplicated on re-run.
- The terminal emulator is unavailable on a given OS → reported unsupported; the fallback terminal remains.
- Fonts already installed → detected and skipped, not re-downloaded.
- A vendor repo for a tool is already configured → not re-added.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST install each modern CLI tool as its own self-contained module (one tool = one module), each idempotent and verify-guarded by the tool's real binary name.
- **FR-002**: The system MUST install the AI agent CLI via the runtime manager from base, declaring that prerequisite so it is installed only after the runtime is available.
- **FR-003**: The system MUST install the default prompt and wire its initialization into the interactive shell startup, applying the shipped opinionated prompt configuration.
- **FR-004**: The system MUST apply the curated shell configuration (aliases, functions, rc) to the user's shell startup.
- **FR-005**: The system MUST install the primary terminal emulator and apply its shipped configuration (theme, font, keybinds), leaving the platform's fallback terminal available.
- **FR-006**: The system MUST install the required developer fonts and make them detectable by font tooling; already-installed fonts MUST be skipped.
- **FR-007**: The system MUST initialize the shell integrations (smart history, directory-jump, fuzzy-find, per-directory environments) in the shell startup, without duplicating entries on re-run.
- **FR-008**: The system MUST apply the terminal multiplexer configuration imported verbatim from the reference setup.
- **FR-009**: All shipped configuration MUST be applied from dev-boost's chezmoi-managed source tree, and every apply MUST be idempotent (re-applying changes nothing and does not duplicate shell-startup entries).
- **FR-010**: Every module MUST be idempotent and verify-guarded: a top-level verify determines already-satisfied state and is evaluated before any install/apply action.
- **FR-011**: OS differences (package names, vendor repos, font/terminal availability) MUST be expressed as per-OS data resolved by the platform precedence, with the reference OS fully supported and an unmatched OS reported as unsupported (a failure), never silently skipped.
- **FR-012**: Dependency ordering MUST be expressed via `requires` (e.g. the AI agent CLI after the runtime manager; config-apply after the relevant tool is installed), reusing the engine's existing ordering — no engine control-flow change.
- **FR-013**: A failure in any module MUST name the module and the exact operation that failed.
- **FR-014**: No module may write secrets into version control or leave credential/state files world-readable (carried from the platform's security rules); shipped configs MUST contain no secrets.

### Key Entities *(include if feature involves data)*

- **CLI tool modules**: the modern command-line utilities (one module each) and the AI agent CLI (runtime-dependent).
- **Prompt + shell config**: the default prompt, its opinionated configuration, and the curated shell rc/aliases/functions.
- **Terminal emulator + fonts**: the primary terminal with its shipped config, and the developer fonts it and the prompt require.
- **Shell integrations**: smart-history, directory-jump, fuzzy-find, per-directory-environment initializers wired into the shell startup.
- **Dotfiles source**: dev-boost's chezmoi source tree holding the shipped configs (prompt, shell rc, terminal, multiplexer, integrations).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the cli + shell profiles on a base machine completes with **zero interactive prompts** and ends with all modules verifying green.
- **SC-002**: Re-running cli + shell is a **no-op** — every module reports already-satisfied and no shell-startup entry is duplicated.
- **SC-003**: After the run, a new interactive shell shows the opinionated prompt and has the smart-history, directory-jump, fuzzy-find, and per-directory-environment integrations active.
- **SC-004**: After the run, the primary terminal emulator opens with the shipped theme/font and the required fonts are detectable by font tooling.
- **SC-005**: The terminal/prompt/multiplexer experience matches the imported reference configuration (same key behaviors and appearance).
- **SC-006**: Adding support for another operating system to any module is a **single new per-OS key**, with no change to engine control flow.
- **SC-007**: Automated tests cover each module's install/apply + idempotent re-run, the unsupported-OS path, the runtime-dependent tool ordering, and the no-duplicate-shell-entry guarantee, with no real installs or network (mocked).

## Assumptions

- Base (Spec 2) is present: the runtime manager, the dotfiles manager, the extra repos, and the package tuning are available; this feature builds on them.
- The reference operating system is fully supported; other OS families are schema-supported and may be thinner (per-OS keys added as needed).
- The shipped configs are dev-boost's curated set in its chezmoi source tree; a user's personal dotfiles overlay (if any) is out of scope for this feature.
- The default prompt is starship; oh-my-posh remains a separate opt-in profile (out of scope).
- "Modern CLI tools" is the design-doc `cli` set (incl. the user-requested bat + btop); the exact list and per-OS package names are pinned in the plan, not the spec.
- This feature is built test-first with the project's existing harness, mocking package managers / font installs / config-apply / external services so no real installs or network occur.
