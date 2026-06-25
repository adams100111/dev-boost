# Architecture

dev-boost is a **small legible engine + declarative data**. The engine never changes to add a tool.

## Layers
- **`bin/devboost`** — CLI dispatch: `install/verify/list/doctor/add/export/diff/update/self-update/dev`.
- **`lib/`** — engine + feature helpers: `log.sh`, `os.sh`, `toml.sh` (TOML→JSON via python3), `module.sh`,
  `depsort.sh` (Kahn topo-sort by `requires`), `profile.sh` (`profile_expand`), `install.sh` (verify-guarded
  loop + summary), `pkg.sh`; feature libs `secrets.sh`, `github.sh`, `fresh.sh`, `gnome.sh`, `vault.sh`,
  `lifecycle.sh`, `devhygiene.sh`, `gpu.sh`.
- **`modules/<name>/module.toml`** — one tool: `name/category/requires/profiles/verify` + per-OS `[install]`.
  Complex tools add `install.sh` (sourcing `lib/log.sh`+`lib/pkg.sh`) and `verify.sh`.
- **`profiles.toml`** — named module sets; `profile_expand` resolves (and transitively pulls `requires`).
- **`devboost.lock`** — deterministic sorted resolved-version manifest (reproducibility).

## Flow
`install` → `profile_expand` → `depsort` → per module: `verify` (skip if green unless `--force`) →
best-match `[install]` → re-verify → record → timed summary. Idempotent + resumable; a failure names the
module + exact command. Cross-OS is data: a module without an `[install].<os>` key is *unsupported* there.

## Engines (dual)

Per the constitution (v2.0.0), the engine may be implemented as pure Bash OR as a
strictly-typed Python engine shipped as a frozen single-file binary (no Python runtime
on the target). Both consume the same declarative TOML modules + `profiles.toml`:

- **Bash engine** — `bin/devboost` + `lib/*.sh` (the original; Fedora-reference, zero-config USB path).
- **Typed-Python engine** — `engine/devboost/` (Typer CLI), with the portable
  `terminal`/`devtools` tiers, headless auto-skip, and a distro→mise→script fallback ladder.

Design specs: `docs/superpowers/specs/2026-06-19-devboost-platform-design.md`,
`2026-06-25-portable-two-tier-installer-design.md`, `2026-06-25-ubuntu-parity-portable-tiers-design.md`.

## Principles (constitution)
Engine+Data separation · Idempotent & verify-guarded · Reproducible (pinned, repo is source of truth) ·
Unattended by default · Test-first (bats) · Cross-OS via data (Fedora reference).
