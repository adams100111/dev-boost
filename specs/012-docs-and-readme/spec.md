# Feature Specification: docs-and-readme

**Feature Branch**: `012-docs-and-readme` | **Created**: 2026-06-21 | **Status**: Draft

**Input**: "docs-and-readme — front-door README (generated profiles table + commands) + docs/ set."

## User Scenarios & Testing *(mandatory)*

Make the repo legible and trustworthy: a usage-first front-door `README.md` and a `docs/` set, with the
profiles table + commands **generated from source** (profiles.toml + bin/devboost) so docs never drift
(design §9b). Documentation feature — no engine/module changes.

### User Story 1 - A newcomer can install from the README (Priority: P1)
The README states what dev-boost is, the 60-minute recovery promise, the one-command quick start, the
`--profile` selector, the full profiles table, and the CLI commands — copy-pasteable.
**Independent Test**: README contains the quick-start command, a profiles table listing EVERY profile
in profiles.toml, and every CLI verb (install/verify/list/doctor/add/export/diff/update/self-update/dev).
**Acceptance**:
1. **Given** profiles.toml, **When** the README profiles table is checked, **Then** every profile name appears (no drift).
2. **Given** bin/devboost verbs, **When** the README Commands section is checked, **Then** every verb is documented with a one-line description.

### User Story 2 - The profiles table is generated, not hand-maintained (Priority: P2)
A generator emits the profiles table from profiles.toml so it can be regenerated and verified, keeping
the README truthful as profiles change.
**Independent Test**: run the generator → its output lists each profile + members; a test asserts the
README's table matches the generator output (in sync).
**Acceptance**:
1. **Given** the generator, **When** run, **Then** it prints a markdown table of every profile and its modules from profiles.toml.
2. **Given** the README, **When** compared to the generator output, **Then** they are in sync (test fails on drift).

### User Story 3 - Deep docs exist for each subsystem (Priority: P3)
`docs/` carries architecture, recovery-runbook, adding-a-module, maintenance, obsidian-sync, ventoy.
**Independent Test**: each docs file exists and contains its key headings/content.
**Acceptance**:
1. **Given** docs/, **When** listed, **Then** architecture.md, recovery-runbook.md, adding-a-module.md, maintenance.md, obsidian-sync.md, ventoy.md all exist with substantive content.

### Edge Cases
- Profiles table must reflect profiles.toml exactly (CI-gated by the sync test) — adding a profile without updating the README fails the test.
- README must document all current verbs (Spec 9 added add/export/diff/update/self-update/dev).
- Docs reference real artifacts (ventoy/ks.cfg, lib/vault.sh, etc.); no dead promises.

## Clarifications
### Session 2026-06-21 (self-resolved, design §9b oracle)
- Q: how is the profiles table kept truthful? → A: a generator script `scripts/gen-profiles-table.sh`
  emits it from profiles.toml; a bats test asserts the README contains every profile (drift-gated). [FR-002,003]
- Q: which docs files? → A: architecture, recovery-runbook, adding-a-module, maintenance, obsidian-sync,
  ventoy (design §9b). recovery-runbook may reference ventoy/Docs/recovery-runbook.md. [FR-004]
- Q: scope? → A: docs only — no engine/module/profile changes. [Assumptions]

## Requirements *(mandatory)*
- **FR-001**: `README.md` MUST be the usage-first front door: what-it-is + recovery promise, quick start
  (one command + `--profile`), profiles table, CLI commands, recovery walkthrough, adding-a-tool example,
  requirements/OS matrix.
- **FR-002**: A generator (`scripts/gen-profiles-table.sh`) MUST emit a markdown profiles table from
  `profiles.toml` (every profile + its modules).
- **FR-003**: A test MUST assert the README lists every profile in profiles.toml and every bin/devboost
  verb (drift-gated).
- **FR-004**: `docs/` MUST contain architecture.md, recovery-runbook.md, adding-a-module.md,
  maintenance.md, obsidian-sync.md, ventoy.md, each with substantive content.
- **FR-005**: Docs-only — NO engine/module/profile changes; the existing suite stays green.

## Success Criteria *(mandatory)*
- **SC-001**: A newcomer can install from the README alone (quick start + profile selector present).
- **SC-002**: The profiles table never drifts — the sync test fails if a profile is added without updating docs.
- **SC-003**: All six docs files exist with real content; the full suite stays green.

## Assumptions
- Design §9b is the oracle; the engine README seed is expanded into the platform front door.
- Generated artifacts (profiles table, command list) are kept truthful by tests, not manual vigilance.
- Docs-only feature: no profiles.toml/module/engine changes.
