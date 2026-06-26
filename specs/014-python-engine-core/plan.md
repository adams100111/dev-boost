# Implementation Plan: Bash → Python Migration (typed engine, modules, and tests)

**Branch**: `main` (greenfield; spec dir `specs/014-python-engine-core`) | **Date**: 2026-06-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-python-engine-core/spec.md`; design doc
`docs/superpowers/specs/2026-06-26-python-engine-migration-design.md`.

## Summary

Rewrite the complete dev-boost platform from bash (≈9.6k LOC `lib/*.sh` + ~55 modules with
`install.sh`/`verify.sh`, 1,104 bats tests) into a single strictly-typed Python codebase, keeping
bash only as the irreducible bootstrap stub (`get.sh` + Kickstart `%post`). Shipped as one
greenfield deliverable (no intermediate release). The engine, all commands, and every module's
install/verify logic become typed Python; side effects flow through one injected `Executor`; modules
are pure-Python files composing a typed primitives library, with an opt-in per-OS `Installer`
strategy. Fedora is implemented for behavioral parity; OS-dispatch seams make Ubuntu a thin later
spec. Delivered as a frozen per-arch binary (PyInstaller). Built as a direct incremental rewrite
across internal milestones M0–M10 (M0 = foundation + one tracer module), each keeping `main` green;
the bash engine + bats are the behavioral spec, ported to pytest and deleted group-by-group.

## Technical Context

**Language/Version**: Python 3.12+ (`.python-version` = 3.12; constitution floor ≥3.11). Synchronous.

**Primary Dependencies**: Typer (CLI; `Annotated` typed params — verified current via context7,
`/websites/typer_tiangolo`, past 0.21, pyreview uses ≥0.25.1), Pydantic v2 + pydantic-settings
(models/config), loguru (logging), tenacity (retry for network ops only). Build: `uv` + `uv_build`.
Freeze: PyInstaller `--onefile` (already proven in-repo via `scripts/build-bundle.sh` + `release.yml`).
Dev: pytest (+ pytest-mock), mypy, ruff. No async runtime.

**Storage**: Filesystem only — `profiles.toml` (declarative data), `devboost.lock` (reproducibility
lock), dotfiles via chezmoi, `age`-encrypted secrets bundle. No database. Static data
(`profiles.toml`, templates, dconf dumps, repo defs) bundled inside the frozen binary and resolved
via a `resources` helper.

**Testing**: pytest with `unit` (hermetic, default) / `integration` markers; a recording
`FakeExecutor` injected so no real `dnf`/`flatpak`/network runs in unit tests; `tmp_path` for FS;
`mypy --strict` + ruff as gates; a frozen-binary smoke test (`--version`/`list`) in CI; real Fedora
VM/container installs for end-to-end parity at milestone boundaries.

**Target Platform**: Linux, Fedora reference (x86_64 + aarch64). Frozen single-file binary, no Python
runtime required on the target. OS-dispatch seams present for other distros (not implemented here).

**Project Type**: Single CLI application / system-bootstrap engine. src-layout Python package
(`engine/src/devboost/` during the rewrite; hoisted to repo root at M10).

**Performance Goals**: Not latency-bound. Engine overhead negligible vs. package installs;
re-running is a fast verify-guarded no-op. No hard throughput target (installs serialize on the
package manager). Frozen-binary cold start should be comparable to the current bash entrypoint.

**Constraints**: Zero runtime dependency on the target (frozen binary); unattended/no prompts;
idempotent + verify-guarded; `mypy --strict` clean; only `get.sh` + Kickstart `%post` may be bash;
secrets decrypted at bootstrap, never in git. Offline except for package/tool downloads.

**Scale/Scope**: ~55 modules → ~55 typed module files; ~25 profiles (+ a new `full` aggregate);
~9.6k LOC bash + 17 `lib/*.sh` subsystems → typed Python engine + primitives; 1,104 bats tests →
comprehensive pytest. 12 CLI verbs. Single deliverable across 11 internal milestones (M0–M10).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v3.0.0 (typed Python + Typer is the single engine/command language; bash only a
non-logic bootstrap stub; pytest + `mypy --strict` gates).

| Principle | Status | How this plan satisfies it |
|---|---|---|
| I. Engine + Data Separation | ✅ PASS | Engine is typed Python+Typer; capability lives in typed module declarations + declarative `profiles.toml`. Adding a tool = one typed file; OS dispatch lives in primitives, not control flow. |
| II. Idempotent & Verify-Guarded | ✅ PASS | `verify(ctx) -> bool` guard; verify-guarded install loop; failures name module + failing command; unsupported → reported skip, never silent. |
| III. Reproducible — Repo is Source of Truth | ✅ PASS | Versions pinned (`pyproject.toml`, `.python-version`, `devboost.lock`); no auto-commit; secrets gitignored. |
| IV. Unattended by Default | ✅ PASS | No interactive prompts; secrets pre-provisioned (age); frozen binary runs headless. |
| V. Test-First (TDD, NON-NEGOTIABLE) | ✅ PASS | Each unit built test-first with pytest + `FakeExecutor`; bats assertions ported as the behavioral spec; merge requires green pytest + `mypy --strict`. |
| VI. Cross-OS via Data | ✅ PASS | OS differences expressed as typed data (`OsMap`, per-OS `Source`/`Installer`) resolved `distro → family → default`; no engine branching; Fedora implemented, seams for others. |
| Tech & Security Constraints | ✅ PASS | Strictly-typed Python + Typer; `tomllib` for TOML; no other interpreters; frozen per-arch binary; bash only `get.sh` + Kickstart `%post`; Conventional Commits, no attribution. |
| Dev Workflow & Quality Gates | ✅ PASS | pytest green + `mypy --strict` + ruff before merge; durable artifacts in spec/docs. |

**Gate result: PASS** — no violations; Complexity Tracking not required. One scheduled
*clarification* (PATCH, M10): reword Principle I's TOML "manifest/`[install]` key" language to
describe modules as typed Python declarations (tracked in design §12), not a violation.

## Project Structure

### Documentation (this feature)

```text
specs/014-python-engine-core/
├── plan.md              # This file
├── research.md          # Phase 0 output — open-question resolutions + tech decisions
├── data-model.md        # Phase 1 output — entities (Module, Profile, Primitive, Executor, Plan, OsInfo…)
├── quickstart.md        # Phase 1 output — runnable validation scenarios
├── contracts/           # Phase 1 output — CLI verb schemas + Module/Installer/Executor/primitive Protocols
│   ├── cli.md
│   └── module-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
engine/                          # typed project during the rewrite; hoisted to repo root at M10
├── pyproject.toml               # uv_build, py>=3.12; typer/pydantic/pydantic-settings/loguru/tenacity; dev: pytest/mypy/ruff
├── .python-version              # 3.12
├── src/devboost/
│   ├── cli/                     # Typer app, one file per command group (app.py + install/verify/list/doctor/lifecycle/devhygiene)
│   ├── core/                    # settings, osinfo, graph (toposort), plan, runner, registry, profiles, errors, log
│   ├── exec/
│   │   ├── executor.py          # Executor Protocol, RealExecutor, FakeExecutor
│   │   └── primitives/          # pkg, flatpak, copr, config, dconf, mise, systemd, age, github, gpu, fs, shell
│   ├── modules/                 # ~55 typed modules, one file each (ddev.py, docker.py, …)
│   └── model.py                 # Module base / Installer Protocol + @register
├── tests/                       # pytest mirror (conftest = FakeExecutor + fixtures); core/ exec/ primitives/ modules/ cli/
└── data/                        # bundled static data: profiles.toml, templates/, dconf dumps, repo defs

get.sh                           # bash bootstrap stub (download + SHA256-verify + exec) — stays
ventoy/ks.cfg                    # Kickstart %post → calls the binary directly (rewritten at M0)
.github/workflows/release.yml    # per-arch frozen binary build (x86_64 + aarch64)

# Deleted across milestones (reference/spec only): lib/*.sh, modules/*/ (bash), bin/devboost,
# install.sh logic, tests/*.bats
```

**Structure Decision**: Single src-layout Python package under `engine/` (matches the `pyapps/pyreview`
house style and avoids colliding with the shrinking bash tree + root bats suite during the rewrite),
hoisted to the repo root at M10 once bash is gone. `profiles.toml` stays at repo root / bundled in
`data/` as the one declarative file. The bash tree coexists transiently as the behavioral spec and is
deleted group-by-group.

## Complexity Tracking

> No constitution violations — section intentionally empty.
