# Feature Specification: Bash → Python Migration (typed engine, modules, and tests)

**Feature Branch**: `014-python-engine-core`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "@docs/superpowers/specs/2026-06-26-python-engine-migration-design.md" — convert the complete dev-boost platform from a bash base to a typed-Python base, keeping bash only where Python genuinely cannot be used. Delivered as one greenfield rewrite, shipped only when complete.

## Scope of this spec *(read first)*

This spec covers the **entire** bash→Python migration as **one deliverable**. The repository is
**greenfield** (not yet in use) and **nothing is published until the migration is 100% complete** —
there is no half-migrated release. Accordingly the work is free to restructure the repo and is built
as a **direct, incremental rewrite** (milestones keep it green, but they are internal build steps,
**not** release points). **Fedora is the implemented target** (behavioral parity with today); the
OS-dispatch architecture is built so other OSes (e.g. Ubuntu) are a thin **later** spec, not
delivered here. The design doc's milestones M0–M10 live in `plan.md`/`tasks.md`, not as separate
specs.

## Clarifications

### Session 2026-06-26

- Q: Is this one spec/deliverable or many shippable phases? → A: **One spec, one deliverable.** Greenfield repo, **not published until the full migration is complete**; phases are internal milestones, not releases.
- Q: Strangler-with-adapter (keep a running product) or direct rewrite? → A: **Direct incremental rewrite.** No legacy shell adapter, no bash-delegation bridges; unported pieces simply don't exist yet (acceptable — nothing is used until complete). The bash engine/modules/bats are the **behavioral spec**, deleted group-by-group as ported.
- Q: Fate of the existing `engine/` Python code? → A: **Rewrite clean** to the house style, cribbing proven algorithms (toposort, OS detect, plan/run); discard `module.toml` loading and the `bash -lc` runner.
- Q: External tools — shell out or Python libraries? → A: **Shell out via the injected `Executor`** for system tools (`dnf`/`flatpak`/`mise`/`chezmoi`/`age`/`dconf`/`git`/`mkcert`); stdlib in-process only for **pure data** (`json`/`tomllib`) and the **GitHub API** (HTTP).
- Q: OS scope of the migration? → A: **Fedora implemented (parity); architecture Ubuntu-ready.** Land the OS-dispatch seams; implement + validate Fedora only. Ubuntu is a later spec.
- Q: The default `full` profile is undefined in `profiles.toml` — what about it? → A: **Define `full`** as the production aggregate (data-only `profiles.toml` change) so there is a real default to validate against.
- Q: CLI verbs not yet ported during the build? → A: Each verb is **ported to Python at its module-group milestone**; there is **no bash delegation** — before its milestone a verb simply isn't present (acceptable, nothing is used until complete).
- Q: Entrypoints? → A: Targets run the **frozen binary as `devboost`**; `ks.cfg`/firstboot call it directly; `bin/devboost` + `install.sh` logic are removed (dep-ensure folded into a Python preflight). Source/CI uses `uv run devboost`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A fresh Fedora machine reaches the same workstation, driven by typed Python (Priority: P1)

An operator bootstraps a fresh Fedora machine (`curl … | bash`, or the frozen binary). The result
is the same fully-configured developer workstation the bash platform produced — same modules
installed, same effects — now produced entirely by the typed-Python engine running as a frozen
binary. Re-running is an idempotent no-op.

**Why this priority**: Behavioral parity on Fedora is the migration's correctness contract. If the
rebuilt platform doesn't produce the same workstation, the rewrite has failed.

**Independent Test**: On a throwaway Fedora VM, run `install full` then `verify full`; the same
module set installs in a valid order and verify reports fully green; a second `install full` changes
nothing.

**Acceptance Scenarios**:

1. **Given** a fresh Fedora VM, **When** `install full` runs, **Then** the production module set installs in a valid dependency order and `verify full` is fully green.
2. **Given** an already-installed machine, **When** `install` re-runs, **Then** every module is verify-skipped and nothing is re-installed.
3. **Given** a module whose install fails, **When** the engine runs it, **Then** it reports a failure naming the module and the exact command that failed.

### User Story 2 - The entire platform is readable and debuggable in one typed language (Priority: P1)

A maintainer reads, navigates, and debugs **any** part of the platform — the engine *and* every
module's install/verify logic — as strictly-typed Python: breakpoints, jump-to-definition,
type-checker guarantees. No part of the shipped platform requires reading or debugging bash except
the ~30-line bootstrap stub.

**Why this priority**: This is the stated purpose of the migration — a codebase a Python developer
can fully own.

**Independent Test**: A maintainer sets a breakpoint inside a chosen module's `install`, runs that
profile's install in dry-run, and steps through profile expansion → dependency sort → the module's
typed steps, all in one language; the whole codebase type-checks clean under `mypy --strict`.

**Acceptance Scenarios**:

1. **Given** the codebase, **When** the strict type-checker and linter run, **Then** both pass with no errors.
2. **Given** any module, **When** the maintainer inspects it, **Then** its complete install/verify logic, metadata, and dependencies are in one typed Python file (no `.sh`, no `module.toml`).

### User Story 3 - Adding a tool is one typed file; the dependency graph is type-checked (Priority: P1)

A maintainer adds a new installable tool by writing one typed Python module that declares its
metadata, its dependencies (as references to other module classes), and its install/verify logic
composed from the typed primitives library. A mistyped dependency or a non-existent profile is
caught by the type-checker / load-time validation, not at runtime on a user's machine.

**Why this priority**: "Adding a tool = one file" is a core platform principle; making the catalog
typed is a primary benefit of the migration.

**Independent Test**: Add a module referencing a dependency and a profile; introduce a deliberate
bad reference; confirm the type-checker or load-time validation rejects it before any install runs.

**Acceptance Scenarios**:

1. **Given** a new module file, **When** it declares `requires` as class references, **Then** an invalid dependency fails the type-checker / load-time validation.
2. **Given** a module assigned to a profile, **When** the catalog loads, **Then** an unknown profile or a dependency cycle is rejected with a clear error before side effects.

### User Story 4 - Adding another OS later is cheap and localized (Priority: P2)

A maintainer (in a future spec) adds Ubuntu support by implementing one `PackageManager` and filling
per-OS package names/sources only in the modules that genuinely diverge — without editing the
OS-agnostic majority of modules and without touching the engine.

**Why this priority**: The platform's portability promise ("adding an OS = no engine changes") must
survive the migration; this spec must deliver the seams even though it implements only Fedora.

**Independent Test**: With Fedora implemented, confirm the OS-dispatch seams exist: a module using a
plain package name needs no per-OS code, and the package-manager selection is driven by detected OS.

**Acceptance Scenarios**:

1. **Given** an OS-agnostic module, **When** the OS changes, **Then** no edit to that module is required for package-manager dispatch.
2. **Given** a module whose name/source/steps differ per OS, **When** it declares a per-OS map/strategy, **Then** the engine resolves the entry for the detected OS (`distro → family → default`), skipping cleanly as `unsupported-os` when none exists.

### User Story 5 - Comprehensive hermetic tests and strict typing gate every change (Priority: P2)

A maintainer or CI runs the test suite: it exercises the engine, every primitive, every module's
logic, and the CLI verbs without touching the real system (no real package manager, filesystem
mutation, or network), plus strict type-checking and linting. The legacy bats suite is gone.

**Why this priority**: Comprehensive hermetic tests + strict typing are the constitution's gates and
the durable guard for an unattended installer.

**Independent Test**: Run the suite on a host with no system package tools and no network; it passes
and mutates nothing outside its temp sandbox; `mypy --strict` and the linter pass.

**Acceptance Scenarios**:

1. **Given** the suite, **When** it runs without system package tools/network, **Then** all unit tests pass with no real system mutation.
2. **Given** a module's typed install, **When** a test runs it against the recording fake executor, **Then** the test asserts exactly which commands would run, in order.

### User Story 6 - Cold-start delivery is unchanged (Priority: P3)

An operator on a minimal/cold box installs via the same `curl … | bash` one-liner; a per-arch frozen
binary is downloaded, verified, and run with no language runtime required on the target.

**Why this priority**: The cold-start, zero-runtime promise is central to the mission and must be
preserved.

**Independent Test**: On a box without Python, run the bootstrap; the frozen binary downloads,
SHA256-verifies, and executes; `devboost --version`/`list` work.

**Acceptance Scenarios**:

1. **Given** a target without a Python runtime, **When** the bootstrap runs, **Then** the matching per-arch binary is fetched, verified, and executed.
2. **Given** the built binary, **When** smoke-tested in CI, **Then** `--version` and `list` succeed for both architectures.

### Edge Cases

- **Unsupported OS / missing per-OS entry**: a module with no path for the detected OS is reported/skipped as `unsupported-os`, never silently ignored, never a crash.
- **Headless host**: GUI-only modules are skipped on a no-display machine; the same command works everywhere.
- **Unknown module / dangling dependency**: a profile or `requires` referencing a non-existent module is rejected at load time, before side effects.
- **Dependency cycle**: detected and reported deterministically (no infinite loop).
- **`--force`** re-installs even when verify passes; **`--dry-run`** prints the plan with no side effects.
- **Install failure**: surfaces the module name and the exact failing command.
- **Partial install / resumability**: re-running after a mid-profile failure does only what is still missing (verify-guarded).
- **Frozen-binary resource paths**: bundled data (profiles, templates, dconf dumps) resolves correctly both from source and inside the binary.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The engine, every command, and every module's install/verify logic MUST be implemented in strictly-typed Python; the only bash that may remain in the shipped product is the bootstrap stub (`get.sh`) and the Kickstart `%post`, which MUST contain no capability, module, or decision logic.
- **FR-002**: Each installable module MUST be a single typed Python file declaring its metadata (name, category, description, GUI flag), its dependencies as **references to other module classes**, the profiles it belongs to, and its `install`/`verify` behavior. No `module.toml` and no per-module `.sh`.
- **FR-003**: All side effects (running external commands, filesystem, network) MUST flow through a single injected executor abstraction, enabling a real executor in production and a recording fake in tests. No module may call subprocess directly.
- **FR-004**: System tools (`dnf`/`flatpak`/`mise`/`chezmoi`/`age`/`dconf`/`git`/`mkcert`, etc.) MUST be invoked via that executor (the canonical CLIs); pure data MUST use stdlib (`json`/`tomllib`) and the GitHub API MUST use in-process stdlib HTTP — not a bundled native-extension library.
- **FR-005**: The engine MUST expand a profile to its modules (through profile membership and `requires`), order them by a deterministic topological sort, and run a verify-guarded, idempotent install loop (skip when verify passes unless forced; else install, then re-verify; record ok/skip/fail).
- **FR-006**: The engine MUST validate the catalog at load time — rejecting unknown module references in profiles or `requires`, and detecting dependency cycles — before any side effect; an invalid module dependency MUST also be catchable by the strict type-checker.
- **FR-007**: The engine MUST detect the host OS and headless state, skip GUI-only modules on headless hosts, and select the package manager from the detected OS. The OS-dispatch seams (package-manager abstraction, per-OS name/source maps, and an opt-in per-OS install-strategy interface) MUST exist so additional OSes need no engine changes.
- **FR-008**: This migration MUST implement and validate **Fedora** only; non-Fedora package managers and per-OS entries are seams to be filled by later specs and are out of scope here.
- **FR-009**: On failure the engine MUST name the failing module and the exact command that failed; an unsupported module MUST be reported (skipped with reason), never silently dropped.
- **FR-010**: The engine MUST support `--dry-run` (print the resolved plan and intended actions, mutate nothing) and `--force` (install even when verify passes).
- **FR-011**: The CLI (built with the mandated typed CLI framework) MUST provide the platform verbs — `install`, `verify`, `list`, `doctor` (incl. `--gpu`), `add`, `export`, `diff`, `update`, `self-update`, `terminal`, `devtools`, and `dev status|gc|down` — with fully type-annotated inputs/outputs and behavior/exit-code parity to today's Fedora behavior.
- **FR-012**: The platform's dependency-ensure preflight (today in `install.sh`) MUST be performed in Python (e.g. via `doctor`); `bin/devboost` and `install.sh`'s logic MUST be removed, and `ks.cfg`/firstboot MUST invoke the frozen binary directly.
- **FR-013**: `profiles.toml` MUST remain the single declarative data file mapping profiles → modules, validated by a typed model on load; it MUST gain a real `full` profile (the production aggregate) as the default install target.
- **FR-014**: The whole codebase MUST type-check clean under `mypy --strict` and pass the linter; these are merge gates.
- **FR-015**: The platform MUST ship as a single self-contained per-architecture frozen binary (x86_64 + aarch64) requiring no language runtime on the target; bundled data MUST resolve correctly from source and frozen, verified by a CI smoke test.
- **FR-016**: The test suite MUST be comprehensive and hermetic (pytest with a fake executor): engine, primitives, every module's logic, CLI verbs, and error paths, with no real system mutation or network in unit tests. The legacy bats suite MUST be fully removed by completion.
- **FR-017**: Behavioral parity MUST be defined against the existing bash engine + bats suite as the specification: each module's behavior is reproduced in Python and its bats assertions ported to pytest; the bash source for a group is deleted once its Python replacement + tests land.
- **FR-018**: The product MUST NOT be published/released until the full migration is complete (no intermediate release); milestones are internal build steps.

### Key Entities *(include if feature involves data)*

- **Module**: a single typed unit with metadata, dependencies (as class references), profile membership, GUI flag, and typed `verify`/`install` behavior composed from primitives (optionally with per-OS install strategies).
- **Profile**: a named, declarative set of modules in `profiles.toml` (the operator's "what to install" knob), including the production aggregate `full`.
- **Primitive**: a typed, idempotent, OS-aware operation (install a package, merge a config, load dconf, …) over the injected executor; the shared vocabulary modules compose.
- **Executor**: the single seam through which all external commands/side effects pass; real in production, a recording fake in tests.
- **Plan**: the ordered list of per-module decisions (install / skip / skip-reason) derived before execution.
- **OS info**: detected distro/family/architecture and headless state driving package-manager selection, per-OS resolution, and GUI skipping.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean Fedora VM, `install full` followed by `verify full` ends fully green, producing the same workstation capabilities the bash platform produced (builds Laravel/.NET+Aspire/Python/Next.js/React-Native out of the box, editors + GUI apps + shell/desktop present).
- **SC-002**: Re-running `install` on an already-installed machine changes nothing (0 modules re-installed) — idempotent no-op.
- **SC-003**: 0% of the shipped product is bash apart from the bootstrap stub (`get.sh`) and Kickstart `%post`; a repository search finds no `lib/*.sh`, no per-module `.sh`, and no `module.toml` in the shipped tree.
- **SC-004**: 100% of installable modules are single typed Python files; the whole codebase type-checks clean under `mypy --strict` and passes the linter.
- **SC-005**: The test suite runs to completion on a host with no system package manager and no network, passing with no real system mutation; the legacy bats suite is removed (0 `.bats` files remain).
- **SC-006**: The frozen per-arch binary builds for x86_64 and aarch64 and passes a CI smoke test (`--version`/`list`) with no Python runtime on the target.
- **SC-007**: A maintainer can step through any module's complete install run in a single language/debugger, with no context switch into bash for any platform logic.
- **SC-008**: Adding an OS-agnostic tool requires exactly one new typed file and no engine edits; a deliberately invalid module dependency is rejected by the type-checker or load-time validation before any install.
- **SC-009**: Test coverage spans all CLI verbs, every primitive, every module, and every identified edge case (unsupported-OS, headless, unknown module, dependency cycle, force, dry-run, install failure, resumable partial install).

## Assumptions

- **Greenfield, single deliverable.** The repository is not yet in use; nothing is published until the migration is complete; the work may freely restructure the repo and rewrite boot artifacts.
- **The language and delivery are fixed by the constitution (v3.0.0)**, not chosen here: strictly-typed Python exposed through Typer, packaged as a frozen single-file per-arch binary, with `pytest` + `mypy --strict` + lint as merge gates. Naming these restates an established constraint, not a new decision.
- **Direct incremental rewrite** (no strangler/adapter): unported pieces simply don't exist until their milestone; the existing bash engine/modules/bats are the behavioral specification, deleted group-by-group as ported.
- **Fedora is the only implemented target**; OS-dispatch seams are delivered but other OSes (Ubuntu, etc.) are later specs.
- **House style follows `pyapps/pyreview`**: src-layout, `uv`, Pydantic models, loguru, custom error hierarchy, injected executor, pytest with markers/fixtures.
- **`profiles.toml` stays the one declarative data file**; any later move of module metadata onto typed classes is out of scope.
- **Verification environment**: parity and end-to-end success are validated on a throwaway Fedora VM/container as module groups complete and at final acceptance; unit tests are fully hermetic and require neither.
- **Milestones M0–M10** from the design doc are internal build steps captured in `plan.md`/`tasks.md`, not separate specs or releases.
