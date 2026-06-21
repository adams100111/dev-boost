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

## Principles (constitution)
Engine+Data separation · Idempotent & verify-guarded · Reproducible (pinned, repo is source of truth) ·
Unattended by default · Test-first (bats) · Cross-OS via data (Fedora reference).
