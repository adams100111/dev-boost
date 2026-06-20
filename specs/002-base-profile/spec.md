# Feature Specification: base-profile

**Feature Branch**: `002-base-profile`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "base-profile — the bedrock layer almost everything `requires` (design doc §5, §10c, §6.4; roadmap Spec 2): system repos + tuned package manager, essential CLI + build tools, and the runtime/container/dotfiles managers (mise + migration, chezmoi, docker)."

## Overview

`base` is the foundation profile every later profile depends on. It makes the package
system fast and complete (extra repos, third-party repos, tuned package manager, full
app catalog), installs the essential command-line and build tools, and stands up the
three managers the rest of the platform builds on: a single **runtime-version manager**
(migrating the machine off any pre-existing fragmented managers), a **dotfiles manager**,
and a **container engine**. It ships as self-contained modules over the existing engine,
reusing the escape-hatch and credential patterns from Spec 1. After this profile, a
machine has a correct, fast, fully-wired base on which stacks, desktop, and apps layer.

## Clarifications

### Session 2026-06-20 (self-answered from the design doc — source of truth; user operating autonomously)

- Q: What credential dependency does the dotfiles manager need? → A: the dotfiles manager clones a possibly-private dotfiles repository over HTTPS using the credential store seeded by Spec 1's `secrets` module; therefore the dotfiles module `requires` `secrets`.
- Q: How is the legacy-runtime-manager migration handled on a machine that has none? → A: the migration step is conditional and idempotent — absent legacy managers ⇒ no-op; present ⇒ read their versions, pin equivalents, install under the new manager, and comment out (never delete) their shell-init blocks.
- Q: Are the simple tool installs one module each or one bundle? → A: one small module per tool (engine principle "adding a tool is one file"), plus a single curated `build-tools` bundle module for the design §10c compiler set.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Package system is complete and fast (Priority: P1)

An operator runs the base profile on a fresh machine. Before anything heavy installs, the
system gains the extra software repositories needed for codecs/drivers and curated
third-party apps, the package manager is tuned for parallel/fast downloads, and the
flatpak app store is wired to the full app catalog — so every later install is fast and
nothing is missing because a repo was absent.

**Why this priority**: Every later module that installs a package or a flatpak depends on
these repos and the tuned downloader being present first. Without it, downstream installs
are slow or fail. This is the irreducible foundation.

**Independent Test**: On a fixture host, run the repo/tuning modules and assert the extra
repos are enabled, the downloader settings written, third-party repos enabled, and the
full app-catalog remote present — each idempotent on re-run.

**Acceptance Scenarios**:

1. **Given** a fresh machine, **When** the foundation modules run, **Then** the free and non-free extra repositories (incl. their app-metadata) are enabled, before any non-free package is installed.
2. **Given** the foundation modules ran, **When** the package-manager config is inspected, **Then** parallel-download and fastest-mirror tuning is present (reconciled, not duplicated).
3. **Given** the foundation modules ran, **When** the app store is inspected, **Then** the full (unfiltered) app-catalog remote is configured and any vendor-filtered default is unfiltered.
4. **Given** the foundation already ran, **When** it runs again, **Then** every module reports already-satisfied (idempotent).

---

### User Story 2 - Essential CLI and build tools are present (Priority: P2)

After the foundation, the operator has the everyday command-line tools and a working
compiler/build toolchain, so they can use the shell productively immediately and later
stacks can compile their native dependencies.

**Why this priority**: Needed for day-one usability and as a prerequisite for stacks that
compile, but the platform's repos (US1) must exist first.

**Independent Test**: Run the tool modules on a fixture host and assert each named tool
verifies present; assert the build-toolchain bundle's key compilers/tools verify; re-run
is a no-op.

**Acceptance Scenarios**:

1. **Given** the foundation is in place, **When** the tool modules run, **Then** each essential CLI tool (version control, transfer, search, archive, monitor, multiplexer, etc.) verifies as installed.
2. **Given** the foundation is in place, **When** the build-tools module runs, **Then** the curated compiler/build bundle verifies as installed.
3. **Given** the tools are installed, **When** the modules run again, **Then** all report already-satisfied.
4. **Given** a host lacking a tool's package on its OS, **When** the module runs, **Then** it is reported unsupported-on-this-OS (a failure), never silently skipped.

---

### User Story 3 - Runtime, container, and dotfiles managers are wired (Priority: P3)

The operator ends with the three managers the rest of the platform relies on: a single
runtime-version manager (migrating the machine off any pre-existing fragmented managers
without changing versions), a dotfiles manager initialized to adopt existing config, and
a working container engine the user can run without elevated privileges.

**Why this priority**: Stacks (runtimes), dotfiles restoration, and containerized
databases/ddev all depend on these, but they sit on top of US1/US2.

**Independent Test**: With fixtures simulating a machine that has / has-not pre-existing
runtime managers, run the manager modules and assert: the runtime manager is installed;
when prior managers exist their versions are preserved and their shell init is disabled
(not deleted); the dotfiles manager is initialized; the container engine is installed, its
service enabled, and the user can use it without elevation. Re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** a machine with no prior runtime managers, **When** the runtime-manager module runs, **Then** it installs cleanly and the migration step is a no-op.
2. **Given** a machine with pre-existing fragmented runtime managers, **When** the module runs, **Then** their current versions are pinned and installed under the new manager, and their shell-init blocks are commented out (not deleted), leaving a clear migration note.
3. **Given** both the new and an old manager are active, **When** the environment check runs, **Then** it warns about the drift.
4. **Given** the dotfiles manager module runs, **When** complete, **Then** the dotfiles manager is initialized and ready to adopt existing config (cloning the dotfiles repo using the credentials provisioned earlier).
5. **Given** the container module runs, **When** complete, **Then** the container service is enabled and the operator can run a container without elevated privileges (after the reported re-login); re-running changes nothing.

### Edge Cases

- A repo/remote already present → detected and skipped, not re-added.
- Tuning file already has the settings → not duplicated; values reconciled.
- The full app-catalog remote already added but the vendor default still filtered → the filter is removed idempotently.
- Legacy runtime managers present but empty (no installed versions) → migration installs nothing, still disables their init blocks.
- The dotfiles repo is unreachable / credentials missing → the manager still installs/initializes; the clone failure is reported (non-fatal by default, fatal under strict).
- The user is already in the container group → not re-added; the group change requires a re-login (reported), not assumed active mid-run.
- A tool's package name differs across OS families → resolved via per-OS data; unknown OS → reported unsupported.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST enable the free and non-free extra software repositories (including their app-metadata) idempotently, and MUST do so before any non-free package is installed.
- **FR-002**: The system MUST tune the package manager for parallel downloads and fastest-mirror selection, writing the settings idempotently (reconcile, do not duplicate).
- **FR-003**: The system MUST enable the curated third-party repositories via the OS's first-party mechanism, idempotently.
- **FR-004**: The system MUST install the app-store tooling and configure the full (unfiltered) app catalog remote, unfiltering any vendor-filtered default.
- **FR-005**: The system MUST install each essential CLI tool as its own self-contained module (one tool = one module), each idempotent and verify-guarded.
- **FR-006**: The system MUST install the curated build/compiler toolchain bundle as a single module, verify-guarded.
- **FR-007**: The system MUST install a single runtime-version manager and MUST perform a conditional, idempotent migration from any pre-existing fragmented managers: preserve their current versions (pin + install under the new manager) and comment out (never delete) their shell-init blocks, leaving a migration note.
- **FR-008**: The environment check MUST warn when both the new runtime manager and a legacy one are active (drift signal).
- **FR-009**: The system MUST install and initialize the dotfiles manager so it can adopt existing configuration, obtaining the dotfiles repository using the credentials provisioned by the secrets feature; a clone failure MUST be non-blocking by default and fatal under strict mode.
- **FR-010**: The system MUST install the container engine, enable its service, and grant the operator non-elevated use (group membership), reporting that a re-login is required for the group change to take effect.
- **FR-011**: Every module MUST be idempotent and verify-guarded: a top-level `verify` determines already-satisfied state and is evaluated before any install action.
- **FR-012**: OS differences (package names, repo-setup commands) MUST be expressed as per-OS data resolved by the platform precedence, with the reference OS fully supported and an unmatched OS reported as unsupported (a failure), never silently skipped.
- **FR-013**: Dependency ordering MUST be expressed via `requires` (e.g. the extra-repos module before any non-free install; the dotfiles manager after the secrets feature), reusing the engine's existing ordering — no engine control-flow change.
- **FR-014**: A failure in any module MUST name the module and the exact operation that failed.
- **FR-015**: No module may write secrets into version control or leave credential/state files world-readable (carried from the platform's security rules).

### Key Entities *(include if feature involves data)*

- **Software repositories**: the extra free/non-free repos, the third-party repo toggle, and the app-catalog remote — external package sources enabled on the machine.
- **Package-manager configuration**: the downloader tuning settings file.
- **Essential tools**: the everyday CLI utilities (one module each) and the build-toolchain bundle.
- **Runtime-version manager + migration record**: the single manager, its pinned version config, and the commented-out legacy init blocks / migration note.
- **Dotfiles manager state**: the initialized dotfiles source and its adopted configuration.
- **Container engine**: the installed engine, its enabled service, and the operator's group membership.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the base profile on a fresh machine completes with **zero interactive prompts** and ends with all base modules verifying green.
- **SC-002**: Re-running the base profile is a **no-op** — every module reports already-satisfied.
- **SC-003**: After the run, installing a non-free package and a flatpak app both succeed on the first attempt (the repos/remotes are present and complete).
- **SC-004**: On a machine that previously used fragmented runtime managers, the runtime versions in use are **unchanged** after migration (no silent upgrades/downgrades), and the legacy managers no longer auto-activate in new shells.
- **SC-005**: After the run, the operator can run a container **without elevated privileges** (after the reported re-login), and the runtime manager, dotfiles manager, and container engine all verify present.
- **SC-006**: Adding support for another operating system to any base module is a **single new per-OS key**, with no change to engine control flow.
- **SC-007**: Automated tests cover each module's install + idempotent re-run, the unsupported-OS path, and the migration's present/absent branches, with no real package installs or network (mocked).

## Assumptions

- The reference operating system is fully supported; other OS families are schema-supported and may be thinner (per-OS keys added as needed).
- Credentials from the prior feature are available for the dotfiles clone; their absence degrades gracefully (clone non-blocking by default).
- "Essential CLI tools" is the design-doc base set (version control, transfer, search, archive, monitor, multiplexer, etc.); the exact list is pinned in the plan, not the spec.
- The migration targets the specific legacy managers named in the design doc; other managers are out of scope for v1.
- Containerized databases and developer tooling are NOT part of this profile (later stack/data features); this profile provides only the container engine itself.
- This feature is built test-first with the project's existing harness, mocking package managers / repo tools / external services so no real installs or network occur.
