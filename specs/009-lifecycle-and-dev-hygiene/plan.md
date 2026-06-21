# Implementation Plan: lifecycle-and-dev-hygiene

**Branch**: `009-lifecycle-and-dev-hygiene` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-lifecycle-and-dev-hygiene/spec.md`

## Summary

Add day-2 lifecycle CLI verbs (`add`, `export`, `diff`, `update`, `self-update`) + a committed
`devboost.lock`, and dev-environment resource-hygiene verbs (`dev status`/`gc`/`down`) with an
`aspire-gc` hourly user timer. **Engine-feature work**: two new libraries (`lib/lifecycle.sh`,
`lib/devhygiene.sh`) + thin `bin/devboost` dispatchers; existing `install/verify/list/doctor` behavior
unchanged. Built **test-first** (Principle V), stubbing all system calls.

## Technical Context

**Language/Version**: Bash (`set -Eeuo pipefail`), same as engine; `jq` + coreutils for parsing.
**Primary Dependencies**: docker (ps/inspect/stats/prune/rm/stop), ddev (poweroff), git (pull),
dnf/flatpak/mise/code (export), systemctl --user + loginctl (aspire-gc) — all PATH-stubbable.
**Storage**: filesystem — `devboost.lock`, `config/mise.toml`, `workstation-config/exports/`,
`~/.config/systemd/user/aspire-gc.*`. No database.
**Testing**: bats; new tests/lifecycle.bats, tests/devhygiene.bats, tests/aspire-gc.bats + bin-dispatch;
stub docker/ddev/code/mise/git; reuse dnf/flatpak/systemctl/loginctl stubs. No real system mutation.
**Target Platform**: Fedora reference; `aspire-gc` module Fedora-only. Verbs are OS-agnostic engine logic.
**Project Type**: dev-boost engine feature (single project).
**Constraints**: idempotent; unattended; read verbs make no mutations; `update`/`self-update` never
auto-commit; reproducible lock; `dev gc` must never false-positive on persistent/live containers.
**Scale/Scope**: 2 libs + 6 verb groups + 1 module + 1 template + lock/config.

## Constitution Check

*GATE: must pass before Phase 0 and re-checked after Phase 1.*

- **I. Engine + Data Separation** — PASS (with rationale). This spec *is* engine-feature work; Principle I
  forbids engine changes to add **tools**, not to add **engine features/verbs**. New libs are additive;
  existing verbs unchanged. The one data module (`aspire-gc`) follows normal module conventions.
- **II. Idempotent & Verify-Guarded** — PASS. `add` refuses overwrite; `export`/`diff`/`dev status`
  read-only; `dev gc` precise + safe; `aspire-gc` idempotent + verify. Failures name the verb + command.
- **III. Reproducible / repo source of truth** — PASS. `devboost.lock` committed + deterministic;
  `update`/`self-update` NEVER auto-commit; secrets never written to lock/export.
- **IV. Unattended** — PASS. No prompts; `dev`/`aspire-gc` non-interactive.
- **V. Test-First (TDD)** — PASS (binding). Every lib fn + verb built RED→GREEN with real assertions on
  stub logs / generated files. No real network/containers/systemd.
- **VI. Cross-OS via Data** — PASS. `aspire-gc` Fedora-only `[install]`; verbs are OS-agnostic logic.

**Result: PASS.** Re-checked post-Phase-1: still PASS — additive libs/verbs, existing engine untouched.

## Project Structure

```text
bin/devboost                       # + cmd_add/export/diff/update/self_update/dev dispatch + usage; install calls lc_lock_write
lib/lifecycle.sh                   # NEW — add/export/diff/update/self-update/lock
lib/devhygiene.sh                  # NEW — dev status/gc/down (docker label+PID orphan GC)
templates/module-skeleton/{module.toml,install.sh}   # NEW — `add` scaffold source
modules/aspire-gc/{module.toml,install.sh,verify.sh} # NEW — hourly `dev gc` user timer
profiles.toml                      # + dev-hygiene = ["aspire-gc"]
devboost.lock                      # NEW — generated, committed, sorted TSV
config/mise.toml                   # NEW (seeded by update)
tests/lifecycle.bats, tests/devhygiene.bats, tests/aspire-gc.bats, tests/cli.bats (dispatch)
tests/fixtures/base/stubs.bash     # + docker/ddev/code/mise/git stub extensions (backward-compatible)
tests/profiles.bats                # + dev-hygiene membership/depsort
```

## Phase 0 — Research
See [research.md](./research.md): new-lib decision, lock TSV, export layout, diff exit codes, update
no-commit, dev gc label+PID detection, aspire-gc timer, add template, stubbing plan. No open unknowns.

## Phase 1 — Design & Contracts
- [data-model.md](./data-model.md): lib function tables, new verbs, artifacts, aspire-gc module, FR map.
- contracts/: lifecycle-verbs, dev-hygiene, aspire-gc-units, devboost-lock.
- [quickstart.md](./quickstart.md): hermetic validation.
- Agent context: CLAUDE.md SPECKIT pointer → this plan.

## Phase 2 — Tasks
`/speckit-tasks` → tasks.md (Setup → Foundational stubs + templates → US1 add → US2 export/diff →
US3 update/lock → US4 self-update → US5 dev status/gc/down → US6 aspire-gc → Polish). NOT created here.
