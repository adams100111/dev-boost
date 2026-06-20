# Feature Specification: editors profile

**Feature Branch**: `006-editors`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "editors profile: VS Code (with a curated extension list) plus the `fresh` terminal editor, both with profile-scoped LSP + formatter provisioning sourced from mise-managed runtimes. Depends on base + shell. See docs/roadmap.md row 6 and the platform design doc."

## Clarifications

### Session 2026-06-20 (self-answered from the design doc + constitution + implemented module patterns — source of truth — and current package docs via context7; user "take over and complete properly")

- Q: How is VS Code installed — sandboxed GUI app, or a native package? → A: the **vendor (Microsoft) package repository** (`code` package), giving the native `code` CLI. This is required so extensions can be provisioned non-interactively (`code --install-extension` / `--list-extensions` as the idempotency check) and so the editor and its tooling see the mise-managed runtimes on PATH; a sandboxed install would defeat both. (Design doc lists "vscode → MS repo" as the per-tool repo pattern; the channel is otherwise a planning detail.)
- Q: Are VS Code's extensions a single curated baseline, or scoped per stack profile? → A: a **single curated baseline list** in this feature (declarative data), installing only what is missing. Richer per-stack VS Code extensions are deferred to the dev-stacks feature (roadmap row 7). Profile-scoping in *this* feature is the `fresh` LSP/formatter mechanism (US3).
- Q: Which editor receives the profile-scoped LSP + formatter provisioning? → A: the **terminal editor `fresh`**. `fresh` needs external language-server/formatter binaries wired into its `config.json`; that wiring is what gets scoped to the selected stacks. VS Code's language intelligence rides on its (baseline) extensions, which bundle their own servers. (Matches the roadmap grammar: "VS Code (+ extension list) **and** `fresh` … with profile-scoped LSP + formatter provisioning".)
- Q: What is the mechanism for "LSP + formatter provisioning sourced from mise-managed runtimes"? → A: each language server/formatter is installed **as a mise-managed tool via mise's package backends** (`mise use -g npm:<tool>@<pin>`, `cargo:`, `go:`, `github:`, `aqua:`), which provisions the tool *and* its runtime, version-pinned (the `@pin` recorded in-repo in the module's `servers.base.tsv`) and shimmed onto PATH. `fresh`'s `config.json` `lsp` block then points each language's `command` at the shimmed binary. This supersedes the legacy `workstation-config/fresh-lsp.sh` raw `npm/cargo/go install` approach.
- Q: What language intelligence does `fresh` get when NO stack profile is selected? → A: a small **always-on base set** (markup/config/shell — e.g. markdown, toml, bash, json/yaml) is provisioned regardless; stack-specific servers/formatters are additive only when their profile is selected.

## User Scenarios & Testing *(mandatory)*

The `editors` profile gives a freshly-bootstrapped developer two ready-to-use code
editors — a graphical one (VS Code, with a curated baseline extension set) and a
terminal one (`fresh`). `fresh` is additionally fitted with the editing intelligence
(completion, diagnostics, format-on-save) for exactly the languages the machine is being
set up to develop in. "The languages the machine is set up for" is determined by which
**stack profiles** (laravel, dotnet, python, web, devops, …) are part of the same
install, so a machine that only builds Python doesn't get .NET language servers it will
never use. (VS Code's per-stack language intelligence is delivered through extensions —
a curated baseline here, richer per-stack sets in the later dev-stacks feature.)

### User Story 1 - VS Code ready with curated extensions (Priority: P1)

A developer finishes bootstrap and opens VS Code. It is already installed and
launches normally, and the team's curated baseline extension set (editorconfig,
language basics, formatting, git, theme to match the terminal aesthetic) is already
present — no manual marketplace hunting. Re-running the installer changes nothing.

**Why this priority**: VS Code is the platform's primary editor; an installed-but-bare
editor still forces every developer to hand-curate extensions, which is exactly the
manual toil the platform exists to remove. This is the smallest slice that delivers
standalone value.

**Independent Test**: Select only the `editors` profile on a supported machine; verify
VS Code is installed and each extension in the curated list is reported as installed;
re-run and verify the run is a no-op (nothing reinstalled).

**Acceptance Scenarios**:

1. **Given** a supported machine with the base profile already applied, **When** the `editors` profile is installed, **Then** VS Code is present and launchable and every extension in the curated baseline list is installed.
2. **Given** VS Code and all curated extensions are already installed, **When** the profile is installed again, **Then** the module verifies as satisfied and performs no reinstall.
3. **Given** VS Code is installed but one curated extension is missing, **When** the profile is installed, **Then** only the missing extension is added and the others are left untouched.

---

### User Story 2 - `fresh` terminal editor ready (Priority: P2)

A developer working in the terminal runs `fresh` (the default terminal editor) and it
opens with a base configuration that matches the rest of the shell environment
(theme/keybindings consistent with ghostty/starship). It is installed and on PATH.
Re-running the installer changes nothing.

**Why this priority**: `fresh` is the platform's chosen default terminal editor; it
complements VS Code for quick edits, remote/SSH sessions, and very large files. It is
independently valuable but secondary to the primary GUI editor.

**Independent Test**: Select the `editors` profile; verify the `fresh` binary is
installed and on PATH and its base configuration is present; re-run and verify no-op.

**Acceptance Scenarios**:

1. **Given** a supported machine with base + shell applied, **When** the `editors` profile is installed, **Then** the `fresh` editor is installed, on PATH, and launches with its managed base configuration present.
2. **Given** `fresh` is already installed, **When** the profile is installed again, **Then** the module verifies as satisfied and performs no reinstall.
3. **Given** the primary install channel for `fresh` is unavailable, **When** the profile is installed, **Then** the documented fallback channel is used so `fresh` still ends up installed, or the run fails naming the editor and the step that failed (never a silent skip).

---

### User Story 3 - Profile-scoped language intelligence in `fresh`, sourced from mise (Priority: P3)

A developer who selected, say, the `python` and `web` stacks alongside `editors` opens
a `.py` or `.ts` file in the `fresh` terminal editor and immediately gets completion,
diagnostics, and format-on-save — without having installed any language server or
formatter by hand. The language servers and formatters that get provisioned are exactly
those matching the selected stacks; they are themselves installed as mise-managed,
version-pinned tools (so their runtimes come from the machine's mise toolchain rather
than ad-hoc system installs) and wired into `fresh`'s configuration. A developer who
selected no stack still gets a small always-on base set (markup/config/shell) but none
of the stack-specific servers.

**Why this priority**: This is the differentiating value of the profile — a terminal
editor that is not just installed but *intelligent for this machine's actual stacks* —
but it depends on US2 (`fresh` must exist first) and is the most complex slice, so it is
sequenced last. (VS Code's per-stack language intelligence is delivered through
extensions; its baseline extension set is US1 and its richer per-stack set is the later
dev-stacks feature.)

**Independent Test**: Install `editors` together with one stack profile (e.g.
`python`); verify the language servers and formatters mapped to that stack are installed
as mise-managed pinned tools and wired into `fresh`'s config, and that a stack NOT
selected (e.g. dotnet) has its servers absent. Re-run and verify no-op.

**Acceptance Scenarios**:

1. **Given** `editors` is installed together with a stack profile, **When** provisioning completes, **Then** the language servers and formatters mapped to that stack are installed as mise-managed tools, pinned to known versions, and wired into `fresh`'s configuration.
2. **Given** a stack profile is NOT selected, **When** provisioning completes, **Then** that stack's language servers/formatters are absent (no unused tooling installed).
3. **Given** `editors` is installed with no stack profile selected, **When** provisioning completes, **Then** only the always-on base set (markup/config/shell intelligence) is wired into `fresh` and no stack-specific servers are installed.
4. **Given** language intelligence is already provisioned for the selected stacks, **When** the profile is installed again, **Then** `fresh`'s configuration is unchanged and nothing is reinstalled (idempotent merge, not overwrite).
5. **Given** a provisioned language server/formatter requires a runtime, **When** it is provisioned, **Then** it and its runtime come from the mise-managed toolchain (version-pinned) and resolve on PATH via mise shims, not from an unmanaged system install.

---

### Edge Cases

- **Unsupported OS**: On a non-supported distribution, the `editors` modules MUST report failure (naming the module), never silently skip — consistent with the platform's unattended-failure contract.
- **Editor missing when language intelligence runs**: If `fresh` language-intelligence provisioning runs but `fresh` is not installed, the run MUST fail naming the editor, rather than half-configuring.
- **Partial extension/server state**: A previously-interrupted run that left some extensions or servers installed MUST be completed on re-run (install only what is missing) without disturbing what is already present.
- **Stack profile added later**: If a stack profile is added in a later install run, re-running `editors` MUST add that stack's servers/formatters without removing or duplicating the existing ones.
- **No graphical session at install time**: VS Code provisioning (including extensions) MUST complete unattended without requiring a logged-in desktop session.
- **Base config ownership conflict**: The editors' base configuration is managed declaratively (dotfiles); profile-scoped language intelligence MUST merge into that config without clobbering the dotfile-owned portions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide an `editors` profile composed of the modules that install and configure the graphical editor (VS Code) and the terminal editor (`fresh`).
- **FR-002**: The `editors` profile MUST declare its dependency on the `base` and `shell` profiles so they are applied first.
- **FR-003**: Installing `editors` MUST install VS Code such that it launches and exposes a way to manage extensions non-interactively.
- **FR-004**: Installing `editors` MUST provision a curated baseline set of VS Code extensions, defined as declarative data (not engine logic), installing only those that are missing.
- **FR-005**: Installing `editors` MUST install the `fresh` terminal editor, placing it on the developer's PATH, with a documented fallback install channel if the primary channel is unavailable.
- **FR-006**: Each editor module's `verify` MUST act as an idempotency guard: a satisfied module is skipped on re-run, and re-running performs only the work that is missing.
- **FR-007**: The set of `fresh` language servers and formatters provisioned MUST be scoped to the stack profiles selected in the same install — a server/formatter for a non-selected stack MUST NOT be installed.
- **FR-008**: An always-on base set of `fresh` language intelligence (for common markup/config/shell file types) MUST be provisioned regardless of which stack profiles are selected, including when none are.
- **FR-009**: Each provisioned `fresh` language server and formatter MUST be installed as a mise-managed tool so that it and any runtime it needs come from the machine's mise-managed, version-pinned toolchain (resolved on PATH via mise) rather than an unmanaged system install.
- **FR-010**: Provisioned language servers and formatters MUST be pinned to known versions (recorded in the repo's version-pin source) so two machines built at different times converge to the same tooling.
- **FR-011**: `fresh` MUST be configured so that the provisioned language servers provide completion/diagnostics and the provisioned formatters provide format-on-save for their mapped file types.
- **FR-012**: `fresh` language-intelligence provisioning MUST merge into `fresh`'s declaratively-managed base configuration without overwriting the dotfile-owned portions, and MUST be idempotent (re-running yields an unchanged config).
- **FR-013**: Any `editors` module MUST report a failure that names the module and the failing step on an unsupported OS or when a required precondition (e.g. a target editor missing) is unmet — never a silent skip.
- **FR-014**: Adding, removing, or changing a curated extension or a stack→server/formatter mapping MUST be a data change (a manifest/list/map edit), not an engine change.
- **FR-015**: The entire `editors` install path MUST complete with zero interactive prompts.

### Key Entities *(include if feature involves data)*

- **editors profile**: The named profile listing the editor modules; selecting it (directly or via `full`) installs both editors and triggers language-intelligence provisioning.
- **Curated VS Code extension list**: Declarative data — the baseline set of extensions every workstation receives, independent of stack.
- **Stack → language-intelligence map**: Declarative data mapping each stack profile (laravel, dotnet, python, web, devops, …) to the language server(s) and formatter(s) it implies, plus an always-on base set.
- **Editor base configuration**: The dotfile-managed base settings for each editor (theme, keybindings, editor defaults) that profile-scoped intelligence merges into.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a single unattended install selecting `editors`, a developer can open VS Code and find 100% of the curated baseline extensions already installed, with zero manual extension installs required.
- **SC-002**: After the same install, running `fresh` from a terminal launches the editor successfully on the first attempt.
- **SC-003**: For every stack profile selected alongside `editors`, opening a file of that stack's primary language in `fresh` yields working completion/diagnostics and format-on-save, with no per-developer setup.
- **SC-004**: For every stack profile NOT selected, none of that stack's `fresh` language servers/formatters are present on the machine (zero unused language tooling).
- **SC-005**: Re-running the `editors` install is a verified no-op: no extension, server, formatter, or config line is reinstalled or rewritten.
- **SC-006**: Two machines built from the same selection at different times end up with identical editor tooling versions (no drift).
- **SC-007**: Every behavior above is covered by automated tests that assert real outcomes, and the existing whole-repo test suite remains green (no regression to the engine or prior profiles).

## Assumptions

- **VS Code install channel** is resolved (see Clarifications): the vendor (Microsoft) package repository, providing the native `code` CLI used for headless, idempotent extension provisioning and mise-PATH visibility.
- **`fresh`** refers to the Rust terminal editor/IDE from getfresh.dev / `sinelaw/fresh` (GPL-2.0), the platform's default terminal editor; primary install via its Fedora `.rpm` (GitHub releases) or official install script, with a `cargo install --locked fresh-editor` fallback. Its config lives at `~/.config/fresh/config.json` (an `lsp` block per language plus a `theme`).
- **VS Code extensions are a single curated baseline**, not profile-scoped, in this feature; stack-specific *VS Code extensions* are deferred to the dev-stacks feature (roadmap row 7). Profile-scoping in this feature applies to `fresh`'s language servers/formatters (US3).
- **The concrete stack→server/formatter mappings** follow the design doc (e.g. intelephense↔laravel, csharp-ls/csharpier↔dotnet, basedpyright/ruff↔python, ts/eslint/prettier/tailwind↔web, terraform-ls↔devops, plus rustfmt/gofmt and the always-on base markup/config/shell servers); concrete tools, mise backends, and pins are finalized in planning.
- **Each `fresh` language server/formatter is installed as a mise-managed tool** via mise's package backends (`npm:`/`cargo:`/`go:`/`github:`/`aqua:`), version-pinned in the repo's mise pin source, rather than via raw `npm/cargo/go` global installs.
- **The editors' base configuration is owned by the existing dotfiles/chezmoi mechanism** (from the shell feature); this feature only adds `fresh`'s profile-scoped intelligence on top via an idempotent merge into `config.json`.
- **Vim mode and other editor personalizations** default to off/standard; they are configuration data, not in scope to decide here.
- **Supported OS for this feature is Fedora**, consistent with the rest of the platform; other distributions report unsupported.
- **The stack profiles themselves** (laravel, dotnet, python, web, devops) are delivered by a later feature (roadmap row 7); this feature provisions intelligence *conditioned on* their selection and must behave correctly when they are present and when they are absent.
