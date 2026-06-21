# Implementation Plan: docs-and-readme
**Branch**: `012-docs-and-readme` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)
## Summary
Expand README.md into the §9b front door; add scripts/gen-profiles-table.sh (profiles table from
profiles.toml); add docs/{architecture,recovery-runbook,adding-a-module,maintenance,obsidian-sync,
ventoy}.md; add tests/docs.bats asserting no drift + docs presence. Docs-only — zero engine/module change.
## Technical Context
Bash generator + markdown. Deps: lib/toml.sh/profile.sh (read profiles), jq, bats. No system mutation.
## Constitution Check
I Engine+Data — PASS (docs/scripts only). II Idempotent — PASS (generator deterministic). III Reproducible
— PASS (generated, drift-gated). IV Unattended — N/A. V Test-First — PASS (drift+presence tests). VI Cross-OS
— N/A. Result PASS.
## Project Structure
README.md ; scripts/gen-profiles-table.sh ; docs/{architecture,recovery-runbook,adding-a-module,
maintenance,obsidian-sync,ventoy}.md ; tests/docs.bats
## Phases: Phase 0 (decisions in spec §Clarifications) · Phase 1 (this plan + data-model below) · Phase 2 tasks.
## Data model: README sections (FR-001); gen-profiles-table.sh (FR-002); docs.bats drift/presence (FR-003);
6 docs files (FR-004).
