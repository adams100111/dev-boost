# Architecture

dev-boost is a **small, legible typed-Python engine + declarative data**. The engine never changes
to add a tool. It is delivered as a **frozen single-file per-arch binary** (PyInstaller) — no Python
runtime on the target.

## Layout (`engine/src/devboost/`)

- **`cli/`** — the Typer app: `install/verify/list/doctor/add/export/diff/update/self-update/term/devtools/dev/accounts/pass/docker`.
  `accounts` is a **standalone sub-app** (never registered as a `Module`; not part of the install plan)
  for creating and managing self-contained, resource-capped Linux sandbox users via `/etc/devboost/users.toml`.
- **`model.py`** — the stable contract: `Ctx`, the `Installer` Protocol, the `Module` base, and the
  typed install sources (`DnfRepo`/`AptRepo`/`Script`, `Source = OsMap[...]`).
- **`core/`** — `osinfo` (+ `OsMap` for `distro→family→default`), `graph` (Kahn toposort over
  `requires`), `profiles` (load + expand), `plan` (skip rules), `runner` (verify-guarded loop),
  `registry` (`@register` auto-discovery + load-time validation), `settings`, `errors`, `log` (loguru).
- **`exec/`** — `executor.py` (the `Executor` Protocol + `RealExecutor` + recording `FakeExecutor`) and
  `primitives/` (the typed, idempotent, OS-aware vocabulary: `pkg`, `flatpak`, `copr`, `mise`, `config`,
  `dconf`, `age`, `github`, `systemd`, `gpu`, `fs`, `shell`, `launchd` (LaunchAgents/Daemons), `tcc`
  (macOS privacy grants), `usermgmt`).
- **`modules/`** — ~100 typed module classes, one declaration each; `requires` are class references.
  `_docker_runtime.py` + `_docker_{colima,orbstack,desktop}.py` — the macOS `DockerRuntime`
  protocol and its three implementations; `_launchd_jobs.py` — `LaunchdTimer`, the macOS twin
  of the systemd `--user` timers.
- **`passstore/`** — the pass multi-device domain (paths, gpg, store layout, git, notify,
  enroll/approve/revoke, sync). Library code only; the `pass`/`pass-store` modules and
  `cli/pass_cmd.py` (`devboost pass`) call into it.
- **`profiles.toml`** (repo root, bundled in the binary) — named module sets; `expand` resolves them
  and `toposort` adds the transitive `requires` closure. `devboost.lock` is the deterministic snapshot.

## Flow

`registry.load()` (validate the whole catalog) → `profiles.expand()` → `graph.toposort()` →
`plan.build_plan()` (headless-GUI / unsupported-OS skips) → `runner.run_plan()`: per module, skip if
`verify(ctx)` and not `--force`; else `install(ctx)`; re-`verify`; record ok/skip/fail. Idempotent +
resumable; a failure names the module and the exact failing command.

## OS dispatch

The package manager is selected once from `ctx.os`: `Dnf` (Fedora), `Apt` (Debian/Ubuntu), `Pacman`
(Arch/Omarchy), `Brew` (macOS — formulae, casks with `--adopt`, taps; never sudo). Per-OS divergence
is typed data — `OsMap` package names, `Source` repos, or opt-in `per_os` `Installer` strategies —
resolved `distro → family → default`. No branching in the engine. A module's `per_os` entry for
the running OS wins (`Module.os_strategy`); for other OSes its own `install()` is the fallback.
The common macOS entries are the `BrewFormula` / `BrewCask` strategies in `modules/_brew.py`.

### User-only steps

`NeedsUser(reason, how_to_fix)` is reported `blocked` with the fix and never fails the run;
`PresentUnmanaged` (an app installed outside dev-boost) is a `skip`. Modules declare macOS privacy
needs as `tcc = (TccGrant(...),)`; the runner blocks them until `devboost permissions --confirm
<module>`.

## Delivery

`scripts/build-bundle.sh` freezes `engine/` (`--collect-submodules devboost` so module auto-discovery
works frozen; bundles `profiles.toml` + `data/` + `templates/`), emits `devboost-<arch>` and the
Ventoy injection archive `devboost-<arch>.tar.gz` (binary at `opt/dev-boost/devboost`).
`.github/workflows/release.yml` builds both arches natively on `v*` tags; `scripts/get.sh` arch-detects,
downloads, SHA256-verifies, and execs. The only bash in the shipped product is `get.sh` and the
Kickstart `%post`.

Design: `docs/superpowers/specs/2026-06-26-python-engine-migration-design.md` (the bash→Python
migration); spec `specs/014-python-engine-core/`.

## GitHub rate limits

Several pinned tools come from GitHub releases: mise resolves seven of them through the
GitHub API (marksman, taplo, k9s, helm, kubectl, opentofu, tofu-ls), and `get.sh` fetches
the devboost binary from a release.

**Unauthenticated, GitHub allows 60 API requests per hour per IP** — not per machine. A
single install stays well inside that, but the budget is shared by everything behind the
same address: a second machine, a CI runner, an office or VPN NAT, or simply installing
twice in an hour. Past the limit GitHub answers `403`, and the affected tools fail to
install.

dev-boost therefore points mise at `gh` for its tokens:

```toml
# ~/.config/mise/config.toml, written by `devboost install mise`
[settings.github]
credential_command = 'gh auth token --hostname "$MISE_CREDENTIAL_HOST"'
```

- **Why a credential command** rather than `GITHUB_TOKEN`: mise runs it on demand, so no
  token is written to a config file or exported into every process's environment. It is
  also per host — `$MISE_CREDENTIAL_HOST` expands to whichever host mise is asking about,
  so a GitHub Enterprise host gets that host's token.
- **`gh` is already part of the `cli` profile** and is authenticated per user, which lifts
  the limit to 5000 requests/hour.
- **It degrades quietly.** If `gh` is missing or logged out the command fails and mise
  falls back to unauthenticated requests — the previous behaviour, never an error.
- **Your own choice wins.** A `credential_command` already set (a work PAT, an Enterprise
  host) is never overwritten.
- `github.credential_command` is one of mise's `global_only` settings: it is honoured in
  the global `~/.config/mise/config.toml` and ignored in a project `mise.toml`.

To check what a machine is using: `mise settings get github.credential_command`, and
`gh auth status` for the token behind it.

## Principles (constitution v3.0.1)

Engine+Data separation (typed Python) · Idempotent & verify-guarded · Reproducible (pinned, repo is
source of truth) · Unattended by default · Test-first (`pytest` + `mypy --strict` + ruff) · Cross-OS
via typed data (Fedora reference; OS-ready seams).
