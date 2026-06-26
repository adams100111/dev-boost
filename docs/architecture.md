# Architecture

dev-boost is a **small, legible typed-Python engine + declarative data**. The engine never changes
to add a tool. It is delivered as a **frozen single-file per-arch binary** (PyInstaller) — no Python
runtime on the target.

## Layout (`engine/src/devboost/`)

- **`cli/`** — the Typer app: `install/verify/list/doctor/add/export/diff/update/self-update/terminal/devtools/dev`.
- **`model.py`** — the stable contract: `Ctx`, the `Installer` Protocol, the `Module` base, and the
  typed install sources (`DnfRepo`/`AptRepo`/`Script`, `Source = OsMap[...]`).
- **`core/`** — `osinfo` (+ `OsMap` for `distro→family→default`), `graph` (Kahn toposort over
  `requires`), `profiles` (load + expand), `plan` (skip rules), `runner` (verify-guarded loop),
  `registry` (`@register` auto-discovery + load-time validation), `settings`, `errors`, `log` (loguru).
- **`exec/`** — `executor.py` (the `Executor` Protocol + `RealExecutor` + recording `FakeExecutor`) and
  `primitives/` (the typed, idempotent, OS-aware vocabulary: `pkg`, `flatpak`, `copr`, `mise`, `config`,
  `dconf`, `age`, `github`, `systemd`, `gpu`, `fs`, `shell`).
- **`modules/`** — ~100 typed module classes, one declaration each; `requires` are class references.
- **`profiles.toml`** (repo root, bundled in the binary) — named module sets; `expand` resolves them
  and `toposort` adds the transitive `requires` closure. `devboost.lock` is the deterministic snapshot.

## Flow

`registry.load()` (validate the whole catalog) → `profiles.expand()` → `graph.toposort()` →
`plan.build_plan()` (headless-GUI / unsupported-OS skips) → `runner.run_plan()`: per module, skip if
`verify(ctx)` and not `--force`; else `install(ctx)`; re-`verify`; record ok/skip/fail. Idempotent +
resumable; a failure names the module and the exact failing command.

## OS dispatch

The package manager is selected once from `ctx.os` (Fedora's `Dnf` implemented; `Apt`/`Pacman` are
seams). Per-OS divergence is typed data — `OsMap` package names, `Source` repos, or opt-in `per_os`
`Installer` strategies — resolved `distro → family → default`. No branching in the engine.

## Delivery

`scripts/build-bundle.sh` freezes `engine/` (`--collect-submodules devboost` so module auto-discovery
works frozen; bundles `profiles.toml` + `data/` + `templates/`), emits `devboost-<arch>` and the
Ventoy injection archive `devboost-<arch>.tar.gz` (binary at `opt/dev-boost/devboost`).
`.github/workflows/release.yml` builds both arches natively on `v*` tags; `scripts/get.sh` arch-detects,
downloads, SHA256-verifies, and execs. The only bash in the shipped product is `get.sh` and the
Kickstart `%post`.

Design: `docs/superpowers/specs/2026-06-26-python-engine-migration-design.md` (the bash→Python
migration); spec `specs/014-python-engine-core/`.

## Principles (constitution v3.0.1)

Engine+Data separation (typed Python) · Idempotent & verify-guarded · Reproducible (pinned, repo is
source of truth) · Unattended by default · Test-first (`pytest` + `mypy --strict` + ruff) · Cross-OS
via typed data (Fedora reference; OS-ready seams).
