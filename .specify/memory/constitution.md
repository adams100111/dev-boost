<!--
SYNC IMPACT REPORT (v3.0.1, 2026-06-26)
PATCH: reworded Principle I + Tech Constraints from TOML "[install] keys / module
manifest / bash -c strings" to the realized typed-Python model (module classes,
typed install/verify over an injected executor, OsMap per-OS entries). No principle
added/removed; reflects the completed bash→Python migration (spec 014).

--- prior report ---
Version change: 2.0.0 → 3.0.0
Bump rationale: MAJOR — removes the co-equal "engine MAY be pure Bash OR
  typed-Python" policy from v2.0.0. The engine and ALL commands/executables MUST now
  be developed in strictly-typed Python with Typer, with fully type-annotated inputs
  and outputs, comprehensive pytest coverage, and `mypy --strict` clean. Delivery to
  targets remains a frozen single-file per-arch binary (PyInstaller) so the target
  needs no Python runtime. Bash is demoted from a sanctioned engine form to a
  non-logic bootstrap stub only (the curl|bash one-liner and Kickstart %post that
  merely fetch, verify, and exec the frozen binary). This is backward-incompatible
  with the dual-engine policy, hence MAJOR.
Principles:
  I.   Engine + Data Separation (engine language now fixed: typed Python + Typer)
  II.  Idempotent & Verify-Guarded
  III. Reproducible — Repo is Source of Truth
  IV.  Unattended by Default
  V.   Test-First (TDD, NON-NEGOTIABLE) — typed, comprehensive
  VI.  Cross-OS via Data (Fedora is the reference)
Modified sections:
  • Core Principle I — the engine language is no longer an implementation detail; it
    is strictly-typed Python exposed through Typer. Capability still lives only in
    declarative TOML data.
  • Technology & Security Constraints — single sanctioned engine path (typed Python +
    Typer, mypy --strict, tomllib, frozen single-file binary). Bash restricted to a
    non-logic bootstrap stub with no capability/decision logic.
  • Development Workflow & Quality Gates — single test gate: the Python engine's
    pytest suite (comprehensive, fully typed) plus `mypy --strict` clean before merge.
    Removed the dual "bats tests/ AND pytest" requirement.
Added/Removed sections: none.
Templates reviewed for consistency:
  ✅ .specify/templates/plan-template.md   — Constitution Check gate accommodates these principles (no edit needed)
  ✅ .specify/templates/spec-template.md   — no new mandatory sections required (no edit needed)
  ✅ .specify/templates/tasks-template.md  — TDD/test-first task ordering still applies (no edit needed)
Deferred TODOs: none.
Follow-up (outside constitution scope): downstream docs/specs that still reference a
  pure-Bash engine or `bats tests/` should be reconciled to the single typed-Python
  engine in their next spec cycle.
-->

# dev-boost Constitution

## Core Principles

### I. Engine + Data Separation

The platform is a small, legible engine plus declarative data. The engine — and
every command and executable the platform ships — MUST be developed in strictly-typed
Python, exposed through Typer (see Technology & Security Constraints). The engine MUST
NOT change when a tool, stack, or operating system is added — those are added as a
typed declaration (a module class, a profile entry in `profiles.toml`, or a per-OS
entry). Every installable thing MUST be a self-contained typed module declaring its
`verify`, its `install`, and its `requires` (as references). Adding a tool MUST be one
file; adding an OS MUST be one localized per-OS entry, never an engine change. Rationale:
extensibility and maintainability come from never editing control flow to add
capability — the highest-frequency change must be the cheapest — and a single typed
language keeps that control flow legible, refactorable, and statically verifiable.

### II. Idempotent & Verify-Guarded

Every operation MUST be safe to re-run. A module's `verify` command is its
idempotency guard: if it passes, the module is skipped (unless `--force`).
Installs MUST be resumable — re-running does only what is missing. A failure MUST
name the module and the exact command that failed; an unsupported module MUST be
reported as a failure, never silently skipped. Rationale: recovery and Day-2
maintenance depend on being able to run the same command repeatedly without harm.

### III. Reproducible — Repo is Source of Truth

The git repository is the single source of truth; machines are disposable
projections of it. Runtime versions MUST be pinned (`config/mise.toml` +
`devboost.lock`) so two machines built weeks apart are identical. Updates MUST be
deliberate: tooling proposes version bumps, a human reviews the diff and commits —
nothing auto-commits. Secrets MUST NOT live in git. Rationale: a recovery platform
is worthless if it cannot reproduce a known-good state on demand.

### IV. Unattended by Default

The primary path MUST complete with zero interactive prompts. Credentials MUST be
pre-provisioned (age-encrypted), never prompted mid-run. Any step that would block
on human input MUST be redesigned to be non-blocking (e.g. upload an SSH key via
API rather than pausing). Rationale: the goal is a configured workstation in
minutes without supervision, including a zero-touch path from USB.

### V. Test-First (TDD, NON-NEGOTIABLE)

Engine and library code MUST be built test-first: write the failing test, confirm
it fails, implement the minimal code to pass, refactor. Tests MUST assert real
behavior (no vacuous assertions) and MUST be comprehensive — every command, every
typed input/output contract, and every error path is covered by `pytest`. A task is
complete only when its tests pass, the code type-checks clean under `mypy --strict`,
and a separate review confirms spec compliance AND code quality. Rationale: a
bootstrap engine runs unattended on a fresh machine — correctness cannot be checked
by hand after the fact, and static types plus comprehensive tests are the only
durable guard.

### VI. Cross-OS via Data (Fedora is the reference)

OS differences MUST be expressed as typed data — per-OS entries (`OsMap`) resolved by the
precedence `<distro>` → `<os-family>` → `default`. Fedora is the reference
implementation; other OSes are schema-supported and may be thinner, but adding
support MUST never require engine changes. Rationale: portability must not become
branching logic in the core.

## Technology & Security Constraints

- **Single engine language.** The engine and every command/executable MUST be
  strictly-typed Python exposed through **Typer**. No other interpreters or
  config-management frameworks are permitted (no Ansible/Salt), and there is no
  parallel Bash engine.
  - All command inputs and outputs MUST be fully type-annotated (Typer
    `Annotated[...]` parameters; typed return/result models). Untyped or `Any`-typed
    public command signatures are not permitted.
  - The code MUST type-check clean under `mypy --strict`.
  - TOML MUST be parsed only via stdlib `tomllib` — never a hand-rolled parser.
- **Frozen-binary delivery.** The engine MUST be shipped to targets as a **frozen
  single-file per-arch binary** (PyInstaller onefile, x86_64 + aarch64) so the target
  needs NO Python runtime installed — preserving the cold-start / minimal-VPS promise.
  Pure-Python source MUST NOT be the on-target runtime.
- **Bash is a non-logic bootstrap stub only.** Shell is permitted solely for the
  thin bootstrap surface that fetches, SHA256-verifies, installs, and execs the frozen
  binary (the public `curl … | bash` one-liner and the Kickstart `%post`). Such stubs
  MUST contain no capability, module, or decision logic — all behavior lives in the
  typed Python engine.
- A module's `install`/`verify` are typed Python methods over an injected executor;
  all external commands run as argv lists (never a shell string). Secrets are decrypted
  at bootstrap from an `age`-encrypted file and MUST remain gitignored. Untracked
  binaries and `.env`/key files MUST stay gitignored.
- Commit messages MUST use Conventional Commits and MUST contain no Claude /
  Anthropic attribution and no `Co-Authored-By` trailer.

## Development Workflow & Quality Gates

- One master design spec governs the platform; each subsystem is delivered through
  its own Spec Kit cycle (`specify → plan → tasks → implement`) or a superpowers
  plan, producing working, testable software on its own.
- Implementation runs test-first with a per-task review (spec + quality) and a
  broad whole-branch review before merge.
- Before any merge to `main`, the typed-Python engine's `pytest` suite MUST be green
  AND the code MUST type-check clean under `mypy --strict`. Test coverage MUST be
  comprehensive across commands, typed I/O contracts, and error paths.
- Reusable knowledge and decisions live in the spec/docs, not only in
  conversation — durable artifacts over ephemeral context.

## Governance

This constitution supersedes other practices for dev-boost. Amendments MUST be made
by editing this file with a Sync Impact Report and a semantic-version bump:
MAJOR for incompatible principle changes/removals, MINOR for added or materially
expanded principles/sections, PATCH for clarifications. Plans and reviews MUST
verify compliance with these principles; deviations MUST be justified in writing or
the work is not done. The design spec and `docs/` carry runtime development guidance.

**Version**: 3.0.1 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-26
