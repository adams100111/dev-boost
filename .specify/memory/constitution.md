<!--
SYNC IMPACT REPORT
Version change: 1.0.0 → 2.0.0
Bump rationale: MAJOR — reverses the "engine is pure Bash; no other interpreters"
  constraint. The engine MAY now be implemented either as pure Bash OR as a
  strictly-typed Python engine shipped as a frozen single-file per-arch binary
  (no runtime interpreter dependency on the target). Driven by the portable
  two-tier installer (terminal/devtools), which is a typed-Python + Typer engine;
  the cold-start/VPS promise is preserved by the frozen binary, not a runtime
  Python dependency. Principle I restated in language-neutral terms.
Principles (unchanged in intent; I reworded):
  I.   Engine + Data Separation (engine language-neutral: Bash or typed-Python)
  II.  Idempotent & Verify-Guarded
  III. Reproducible — Repo is Source of Truth
  IV.  Unattended by Default
  V.   Test-First (TDD, NON-NEGOTIABLE)
  VI.  Cross-OS via Data (Fedora is the reference)
Modified sections:
  • Core Principle I — "small, legible engine" now explicitly may be Bash or
    typed-Python; capability still lives only in declarative TOML data.
  • Technology & Security Constraints — dual engine path; a typed-Python engine
    MUST be strictly typed (mypy --strict), parse TOML via stdlib tomllib, and
    ship as a frozen single-file binary so the target needs no Python runtime.
  • Development Workflow & Quality Gates — both suites (`bats tests/` for the Bash
    engine AND the Python engine's pytest suite) MUST be green before merge.
Added/Removed sections: none.
Templates reviewed for consistency:
  ✅ .specify/templates/plan-template.md   — Constitution Check gate still accommodates these principles (no edit needed)
  ✅ .specify/templates/spec-template.md   — no new mandatory sections required (no edit needed)
  ✅ .specify/templates/tasks-template.md  — TDD/test-first task ordering still applies to both engines (no edit needed)
Deferred TODOs: none.
-->

# dev-boost Constitution

## Core Principles

### I. Engine + Data Separation

The platform is a small, legible engine plus declarative data. The engine MAY be
implemented in pure Bash OR as a strictly-typed Python engine (see Technology &
Security Constraints); the engine language is an implementation detail. Whatever the
language, the engine MUST NOT change when a tool, stack, or operating system is added
— those are added as data (a module manifest, a profile entry, or an install key).
Every installable thing MUST be a self-contained module declaring `verify`, at least
one `[install]` key, and its `requires`. Adding a tool MUST be one file; adding an OS
MUST be one key. Rationale: extensibility and long-term maintainability come from
never editing control flow to add capability — the highest-frequency change must be
the cheapest, regardless of the engine's language.

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
behavior (no vacuous assertions). A task is complete only when its tests pass and
a separate review confirms spec compliance AND code quality. Rationale: a bootstrap
engine runs unattended on a fresh machine — correctness cannot be checked by hand
after the fact.

### VI. Cross-OS via Data (Fedora is the reference)

OS differences MUST be expressed as data — per-OS `[install]` keys resolved by the
precedence `<distro>` → `<os-family>` → `default`. Fedora is the reference
implementation; other OSes are schema-supported and may be thinner, but adding
support MUST never require engine changes. Rationale: portability must not become
branching logic in the core.

## Technology & Security Constraints

- The engine MAY be implemented in one of two sanctioned forms; no other
  interpreters or config-management frameworks are permitted (no Ansible/Salt):
  - **Pure Bash** — external runtime dependencies limited to the system `python3`
    (for stdlib `tomllib` TOML parsing; floor ≥3.11) and `jq`.
  - **Strictly-typed Python** (e.g. Typer CLI) — MUST type-check clean under
    `mypy --strict`, MUST parse TOML via stdlib `tomllib`, and MUST be shipped to
    targets as a **frozen single-file per-arch binary** so the target needs NO
    Python runtime installed (preserving the cold-start / minimal-VPS promise).
    Pure-Python source MUST NOT be the on-target runtime.
- TOML is parsed only via stdlib `tomllib` — never a hand-rolled parser.
- Module `install`/`verify` strings run via `bash -c` under a local-manifest trust
  model; secrets are decrypted at bootstrap from an `age`-encrypted file and MUST
  remain gitignored. Untracked binaries and `.env`/key files MUST stay gitignored.
- Commit messages MUST use Conventional Commits and MUST contain no Claude /
  Anthropic attribution and no `Co-Authored-By` trailer.

## Development Workflow & Quality Gates

- One master design spec governs the platform; each subsystem is delivered through
  its own Spec Kit cycle (`specify → plan → tasks → implement`) or a superpowers
  plan, producing working, testable software on its own.
- Implementation runs test-first with a per-task review (spec + quality) and a
  broad whole-branch review before merge.
- Every engine's full test suite MUST be green before any merge to `main`: the
  Bash engine's `bats tests/` AND (where present) the typed-Python engine's
  `pytest` suite, the latter additionally type-checking clean under `mypy --strict`.
- Reusable knowledge and decisions live in the spec/docs, not only in
  conversation — durable artifacts over ephemeral context.

## Governance

This constitution supersedes other practices for dev-boost. Amendments MUST be made
by editing this file with a Sync Impact Report and a semantic-version bump:
MAJOR for incompatible principle changes/removals, MINOR for added or materially
expanded principles/sections, PATCH for clarifications. Plans and reviews MUST
verify compliance with these principles; deviations MUST be justified in writing or
the work is not done. The design spec and `docs/` carry runtime development guidance.

**Version**: 2.0.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-25
