<!--
SYNC IMPACT REPORT
Version change: (template/unversioned) → 1.0.0
Bump rationale: First ratification — initial set of governing principles for dev-boost.
Principles defined:
  I.   Engine + Data Separation
  II.  Idempotent & Verify-Guarded
  III. Reproducible — Repo is Source of Truth
  IV.  Unattended by Default
  V.   Test-First (TDD, NON-NEGOTIABLE)
  VI.  Cross-OS via Data (Fedora is the reference)
Added sections: Technology & Security Constraints; Development Workflow & Quality Gates; Governance.
Removed sections: none.
Templates reviewed for consistency:
  ✅ .specify/templates/plan-template.md   — Constitution Check gate accommodates these principles (no edit needed)
  ✅ .specify/templates/spec-template.md   — no new mandatory sections required (no edit needed)
  ✅ .specify/templates/tasks-template.md  — TDD/test-first task ordering already supported (no edit needed)
Deferred TODOs: none.
-->

# dev-boost Constitution

## Core Principles

### I. Engine + Data Separation

The platform is a small, legible engine plus declarative data. The engine MUST NOT
change when a tool, stack, or operating system is added — those are added as data
(a module manifest, a profile entry, or an install key). Every installable thing
MUST be a self-contained module declaring `verify`, at least one `[install]` key,
and its `requires`. Adding a tool MUST be one file; adding an OS MUST be one key.
Rationale: extensibility and long-term maintainability come from never editing
control flow to add capability — the highest-frequency change must be the cheapest.

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

- The engine is **pure Bash**; the only external runtime dependencies are the
  system `python3` (for stdlib `tomllib` TOML parsing; floor ≥3.11) and `jq`.
  No other interpreters or config-management frameworks (no Ansible/Salt).
- TOML is parsed only via `python3` `tomllib` — never a hand-rolled parser.
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
- The full test suite (`bats tests/`) MUST be green before any merge to `main`.
- Reusable knowledge and decisions live in the spec/docs, not only in
  conversation — durable artifacts over ephemeral context.

## Governance

This constitution supersedes other practices for dev-boost. Amendments MUST be made
by editing this file with a Sync Impact Report and a semantic-version bump:
MAJOR for incompatible principle changes/removals, MINOR for added or materially
expanded principles/sections, PATCH for clarifications. Plans and reviews MUST
verify compliance with these principles; deviations MUST be justified in writing or
the work is not done. The design spec and `docs/` carry runtime development guidance.

**Version**: 1.0.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-19
