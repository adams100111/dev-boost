# Feature Specification: lifecycle-and-dev-hygiene

**Feature Branch**: `009-lifecycle-and-dev-hygiene`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "lifecycle-and-dev-hygiene — day-2 CLI lifecycle verbs + dev-environment resource hygiene."

## User Scenarios & Testing *(mandatory)*

This feature turns dev-boost from a one-shot installer into a **day-2 platform**: the repo stays the
single source of truth, machines are disposable projections, and every change flows repo → machine
through the same engine (design §8). It also fixes the audit-found resource-starvation class of
problem (orphan/duplicate Aspire AppHosts, design §8b) with explicit hygiene verbs and an automated
garbage collector. This is **engine-feature work** — new CLI verbs in `bin/devboost` + library code —
built test-first.

### User Story 1 - Scaffold a new module in seconds (Priority: P1)

A developer wants to add a tool to the platform. They run `devboost add <name>` and get a ready-to-edit
module skeleton (manifest + optional install script) in the right place, so "add a tool = one file"
is literally one command, not hand-copying an existing module.

**Why this priority**: Smallest, fully-independent engine-verb slice; it proves the verb-dispatch +
library pattern and directly serves the mission's "adding a tool = one file" promise.

**Independent Test**: Run `devboost add foo`; assert a new `modules/foo/` with a valid `module.toml`
(name/category/requires/profiles/verify placeholders) is created, that re-running is safe, and that it
refuses to clobber an existing module.

**Acceptance Scenarios**:

1. **Given** no `modules/foo`, **When** `devboost add foo` runs, **Then** `modules/foo/module.toml` is created from the template with `name = "foo"` and the standard fields, and the command prints next-step guidance (add to a profile, fill `[install]`).
2. **Given** `--folder` (or equivalent), **When** `devboost add foo --folder`, **Then** an `install.sh` escape-hatch skeleton is also scaffolded that sources `lib/log.sh` + `lib/pkg.sh`.
3. **Given** `modules/foo` already exists, **When** `devboost add foo` runs, **Then** it refuses (clear error) and does not overwrite the existing module.

---

### User Story 2 - See drift between repo and machine (Priority: P2)

A developer (or a second machine) wants to know whether the box matches the repo. `devboost export`
snapshots what is actually installed; `devboost diff` compares declared (repo) vs actual (machine) and
reports what is missing, extra, or version-mismatched — read-only, no changes.

**Why this priority**: Visibility is the prerequisite for safe day-2 management; independent of the
mutating verbs.

**Independent Test**: With stubbed package tools, run `export` (assert a timestamped snapshot of
dnf/flatpak/mise/VS Code state is written under `workstation-config/exports/`), then `diff` (assert it
reports a declared module not present on the machine, and exits non-zero when drift exists).

**Acceptance Scenarios**:

1. **Given** a machine state, **When** `devboost export` runs, **Then** a timestamped snapshot of actual installed state (dnf user packages, flatpak apps, mise tools, VS Code extensions) is written under `workstation-config/exports/` and the command makes no system changes.
2. **Given** the repo declares modules not satisfied on the machine, **When** `devboost diff` runs, **Then** it lists the drift (declared-but-missing, present-but-undeclared) and exits non-zero.
3. **Given** the machine matches the repo, **When** `devboost diff` runs, **Then** it reports no drift and exits zero.

---

### User Story 3 - Propose version updates reproducibly, never auto-commit (Priority: P3)

A developer wants to bump pinned versions safely. `devboost update` checks upstream / module update
steps, **proposes** new pins into the version files and a committed `devboost.lock`, refreshes
dnf/flatpak/extensions, prints a diff, and stops — the human reviews and commits. Nothing is
auto-committed; two machines built from the same lock are identical.

**Why this priority**: Core reproducibility lever, but builds on the visibility verbs and is riskier,
so it follows them.

**Independent Test**: With stubbed tools, run `update`; assert proposed version changes are written to
the version file(s) + `devboost.lock`, a diff is printed, and no `git commit` is ever invoked.

**Acceptance Scenarios**:

1. **Given** pinned versions and available upstreams (stubbed), **When** `devboost update` runs, **Then** it writes proposed pins into the version config + regenerates `devboost.lock`, prints a human-readable diff, and never runs `git commit`.
2. **Given** `devboost.lock` is absent, **When** any resolving verb runs, **Then** the lock is generated from the currently-resolved versions; **Given** it exists, re-running produces a stable file (idempotent ordering).
3. **Given** `--profile X`, **When** `devboost update --profile X` runs, **Then** only that profile's modules are considered.

---

### User Story 4 - Pull the latest platform and re-validate (Priority: P4)

A developer on a second machine runs `devboost self-update` to fetch the latest dev-boost repo and
immediately re-validate the environment, so propagating a change is two commands
(`self-update && install`).

**Why this priority**: Convenience wrapper over git + existing verbs; additive and low-risk.

**Independent Test**: With a stubbed git, run `self-update`; assert it pulls the repo and then runs the
re-validation (doctor/verify) path, and surfaces a clear message if the pull fails.

**Acceptance Scenarios**:

1. **Given** a clean repo, **When** `devboost self-update` runs, **Then** it updates the repo (git pull) and then re-validates (doctor/verify), reporting the outcome.
2. **Given** the pull fails (offline/conflict), **When** `devboost self-update` runs, **Then** it reports a clear, named error and does not leave the repo half-updated silently.

---

### User Story 5 - Reclaim memory from orphan/duplicate dev orchestrations (Priority: P5)

A developer's machine is starved because a stale duplicate Aspire AppHost is still running its own
postgres/redis alongside a fresh one. `devboost dev status` shows the situation (AppHosts with age +
project, duplicates, per-container RAM, swap pressure); `devboost dev gc` precisely removes only the
**orphaned session** containers (creator PID dead) and prunes exited ones, never touching persistent
infra; `devboost dev down` does an end-of-day reclaim.

**Why this priority**: Directly fixes the audit-found OOM class (design §8b), but depends on nothing
else here and is its own slice.

**Independent Test**: With stubbed docker/ddev/ps, run `dev status` (assert it flags a duplicate live
AppHost), `dev gc` (assert it removes a session container whose creator PID is dead and prunes exited,
but leaves a `persistent=true` container and a session container whose PID is alive untouched), and
`dev down` (assert it powers off ddev, stops stale AppHosts, prunes, and runs gc).

**Acceptance Scenarios**:

1. **Given** two live AppHosts of the same project, **When** `devboost dev status` runs, **Then** it warns about the duplicate and lists AppHost age + project path and per-container RAM/swap pressure.
2. **Given** a DCP session container (label `…persistent=false`) whose creator PID is dead, **When** `devboost dev gc` runs, **Then** that container is removed and exited containers are pruned; **And** a container labelled persistent, and a session container whose creator PID is still alive, are NOT removed.
3. **Given** end of day, **When** `devboost dev down` runs, **Then** it powers off ddev, stops stale AppHosts, prunes stopped containers, and runs `dev gc`.

---

### User Story 6 - Orphans never accumulate (automated GC) (Priority: P6)

So that OOM-driven orphans can't pile up between manual cleanups, an `aspire-gc` user-level timer runs
`devboost dev gc` hourly.

**Why this priority**: Automation hardening on top of US5; lowest priority because the manual verb
already delivers the value.

**Independent Test**: Install the `aspire-gc` module (stubbed); assert a `systemd --user` service +
hourly timer are written and enabled (with linger), the service invokes `devboost dev gc`, and re-runs
are idempotent.

**Acceptance Scenarios**:

1. **Given** the `aspire-gc` module is installed, **When** install runs, **Then** a `systemd --user` oneshot service that runs `devboost dev gc` and an hourly timer are written under `~/.config/systemd/user/` and enabled (linger arranged); re-running is idempotent and verify is green.
2. **Given** a non-Fedora OS, **When** the module is attempted, **Then** the engine reports it unsupported (cross-OS-via-data).

---

### Edge Cases

- **`add` name collision / invalid name**: refuse to overwrite an existing module; reject empty/invalid names.
- **`export`/`diff` with a tool absent** (e.g., no flatpak): degrade gracefully — record what is available, note the gap, never crash.
- **`diff` exit semantics**: zero = in sync, non-zero = drift (so it is CI-usable).
- **`update` upstream unreachable / offline**: report and skip the unreachable check; never partially rewrite the lock into an inconsistent state; never auto-commit.
- **`self-update` with local uncommitted changes / pull conflict**: clear named failure, no silent clobber.
- **`dev gc` with docker absent or no containers**: no-op success, not an error.
- **`dev gc` must never remove persistent infra** (the Spec 7 dotnet template's `persistent=true` + data-volume containers) nor a session container whose creator process is still alive.
- **`aspire-gc` with no graphical session at install** (headless): timer enabled for next session via linger.
- **`devboost.lock` ordering**: deterministic (sorted) so re-generation diffs cleanly and is reproducible.

## Clarifications

### Session 2026-06-21 (self-resolved, design doc = oracle)

Driven autonomously (hands-free directive). Decisions grounded in design doc §4/§8/§8b + constitution:

- Q: `devboost.lock` format? → A: **deterministic, sorted TSV** (`module<TAB>resolved-version`),
  committed (reproducibility anchor), secret-free; written/regenerated by `update` and `install`. [FR-005]
- Q: `export` layout? → A: `workstation-config/exports/<UTC-timestamp>/` with per-source files
  `dnf.txt`, `flatpak.txt`, `mise.txt`, `vscode-extensions.txt`; read-only; missing tool → recorded gap. [FR-002]
- Q: `diff` exit semantics? → A: **0 = in sync, non-zero = drift** (CI-usable). [FR-003, SC-002]
- Q: what does `update` write? → A: proposed pins into `config/mise.toml` (seed if absent) +
  regenerated `devboost.lock`, prints a diff, **never `git commit`**. [FR-004, SC-003]
- Q: `dev gc` orphan detection? → A: a container is GC'd iff label
  `com.microsoft.developer.usvc-dev.persistent == false` **AND** its creator PID is dead (read from
  container metadata/labels); persistent-labelled or live-PID containers are NEVER removed; exited
  containers pruned. [FR-009, SC-004]
- Q: `aspire-gc` automation shape? → A: a Fedora-only data module installing a `systemd --user`
  oneshot service running `devboost dev gc` + an **hourly** timer, linger-enabled, idempotent +
  verify-guarded (mirrors the Spec 8 vault-sync timer conventions). [FR-011]
- Q: `add` scaffold template? → A: the canonical `module.toml` shape (name/category/requires/profiles/
  verify/[install]) + optional `install.sh` escape-hatch sourcing `lib/log.sh` + `lib/pkg.sh`. [FR-001]

No external version verification needed — this is engine-feature work over existing tools (no new tools).

## Requirements *(mandatory)*

### Functional Requirements

**Lifecycle verbs (engine: `bin/devboost` + lib)**

- **FR-001**: The engine MUST provide `devboost add <name> [--folder]` that scaffolds `modules/<name>/module.toml` (and, with `--folder`, an `install.sh` escape-hatch skeleton sourcing `lib/log.sh` + `lib/pkg.sh`) from a template, refusing to overwrite an existing module and rejecting invalid names.
- **FR-002**: The engine MUST provide `devboost export` that snapshots ACTUAL installed state (dnf user packages, flatpak apps, mise tools, VS Code extensions) into a timestamped path under `workstation-config/exports/`, making no system changes; missing tools are recorded as gaps, not failures.
- **FR-003**: The engine MUST provide `devboost diff` that compares declared (repo modules/profiles + pins) vs actual (machine) and reports drift (declared-but-missing, present-but-undeclared, version-mismatch), exiting zero when in sync and non-zero when drift exists; read-only.
- **FR-004**: The engine MUST provide `devboost update [--profile X]` that proposes new pinned versions into the version config and (re)generates `devboost.lock`, refreshes package/extension state, prints a diff, and NEVER runs `git commit` (Principle III).
- **FR-005**: The engine MUST maintain a committed `devboost.lock` of resolved exact versions in a deterministic (sorted) order; it is generated/updated by the resolving verbs and contains NO secrets.
- **FR-006**: The engine MUST provide `devboost self-update` that updates the dev-boost repo (git pull) and then re-validates (doctor/verify), reporting a clear named error on pull failure without leaving a silent half-updated state.
- **FR-007**: New verbs MUST be wired into `bin/devboost` dispatch + `usage`, and MUST NOT change the behavior of the existing `install`/`verify`/`list`/`doctor` verbs.

**Dev-environment resource hygiene**

- **FR-008**: The engine MUST provide `devboost dev status` listing running Aspire AppHosts (age + project path), ddev projects, per-container RAM, and swap pressure, and WARNING when more than one live AppHost exists for the same project.
- **FR-009**: The engine MUST provide `devboost dev gc` that removes ONLY DCP session containers (label `com.microsoft.developer.usvc-dev.persistent=false`) whose creator PID is dead, prunes exited containers, and reports duplicate live AppHosts — and MUST NEVER remove containers labelled persistent or session containers whose creator PID is still alive.
- **FR-010**: The engine MUST provide `devboost dev down` that powers off ddev, stops stale AppHosts, prunes stopped containers, and runs `dev gc`.
- **FR-011**: The system MUST provide an `aspire-gc` data module that installs a `systemd --user` oneshot service (running `devboost dev gc`) + an hourly timer, enables them (arranging linger), is idempotent + verify-guarded, and is Fedora-only (unsupported elsewhere by data).

**Cross-cutting**

- **FR-012**: All read verbs (`export`, `diff`, `dev status`) MUST make no system mutations; all mutating actions MUST be unattended (no prompts) and safe to re-run.
- **FR-013**: The work MUST be built test-first and keep the existing suite green, extending the test harness backward-compatibly and stubbing ALL system calls (dnf/flatpak/mise/code/git/docker/ddev/ps/systemctl/loginctl) — no real network, containers, or system mutation in tests.

### Key Entities *(include if data involved)*

- **Module scaffold**: a new `modules/<name>/` with a templated `module.toml` (+ optional `install.sh`).
- **Export snapshot**: a timestamped record under `workstation-config/exports/` of actual dnf/flatpak/mise/VS Code state.
- **Drift report**: the computed set of declared-vs-actual differences with a pass/fail exit.
- **devboost.lock**: the deterministic resolved-version manifest (module → resolved version), committed, secret-free.
- **AppHost / DCP container view**: the in-memory model of running AppHosts (project, age, PID) and their session/persistent containers used by the `dev` verbs.
- **aspire-gc units**: the user-level oneshot service + hourly timer that run `devboost dev gc`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can scaffold a new, valid module with a single command and zero hand-copying; the scaffold passes the engine's own module validation.
- **SC-002**: `devboost diff` correctly reports "in sync" (exit 0) on a matching machine and "drift" (exit non-zero) when a declared module is missing — usable as a CI gate.
- **SC-003**: `devboost update` never produces a commit; 100% of version changes land as reviewable working-tree edits + a deterministic `devboost.lock`.
- **SC-004**: `devboost dev gc` removes 100% of dead-PID session orphans and 0% of persistent or live-PID containers (no false positives that kill active work).
- **SC-005**: With the `aspire-gc` timer active, orphaned session containers are reclaimed within an hour without any manual action.
- **SC-006**: The full bats suite stays green; all new lifecycle/hygiene logic is covered by tests that use only stubs (no real system mutation).

## Assumptions

- **Engine-feature scope is intended**: this spec deliberately extends `bin/devboost` + `lib/` (new verbs/libs), which is allowed — Principle I forbids engine changes to add *tools*, not to add *engine features*. Existing verbs are untouched in behavior.
- **`devboost.lock` is committed** (reproducibility anchor), unlike secrets which remain gitignored; its format is a deterministic, sorted, secret-free manifest (exact shape finalized in the plan).
- **`config/mise.toml` is the runtime-pin file** referenced by the design; if absent, `update`/lock generation create/seed it from resolved state.
- **AppHost/DCP detection uses Docker labels + container metadata** (`com.microsoft.developer.usvc-dev.persistent`, creator PID) per design §8b; "stale/duplicate" = more than one live AppHost for the same project path, and "orphan" = session container whose creator PID is no longer alive.
- **`dev` verbs operate on the user's Docker/ddev**; with none present they are graceful no-ops.
- **`aspire-gc` runs `dev gc` hourly** (design §8b) as a `systemd --user` unit, mirroring the Spec 8 vault-sync timer conventions (linger for headless first boot).
- **`add`'s template** is the canonical module shape used across Specs 1–8 (manifest fields + escape-hatch install.sh sourcing log/pkg).
