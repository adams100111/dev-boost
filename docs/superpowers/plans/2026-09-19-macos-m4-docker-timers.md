# macOS M4 — Docker Runtimes & launchd Timers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On an Apple Silicon Mac (macOS 27/26), `devboost install docker docker-build-gc ddev aspire data-services aspire-gc` gives a working Docker engine (Colima by default), ddev, Aspire and the data services. `devboost docker use <colima|orbstack|docker-desktop>` switches runtimes and reconfigures everything that depends on Docker. The Linux systemd timers (aspire-gc, restic-backup, restic-b2, obsidian-sync) and the browser-mcp service run on macOS as launchd agents labelled `dev.devboost.<name>`, on the same schedules.

**Architecture:** A `DockerRuntime` protocol (`modules/_docker_runtime.py`) with one implementation per runtime (`_docker_colima.py`, `_docker_orbstack.py`, `_docker_desktop.py`). The runtime is chosen by `DEVBOOST_DOCKER_RUNTIME` > `docker_runtime` in `~/.config/devboost/config.toml` > `colima`. The `docker` and `docker-build-gc` modules get a `per_os.macos` strategy that delegates to the selected runtime. The timer modules get a `per_os.macos` strategy built on a small `LaunchdTimer` helper (`modules/_launchd_jobs.py`) over M1's `launchd.user_agent`. Every Linux code path stays byte-for-byte what it is today. The only new engine surface is a few functions added to the M1 `launchd` and `pkg` primitives, and the `devboost docker` sub-app.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic, pydantic-settings, PyYAML (new, for `colima.yaml`), tomli-w, pytest, mypy `--strict`, ruff, `uv`; launchd plists via stdlib `plistlib`; Homebrew 7; Colima 0.10, OrbStack 2.2, Docker Desktop 4.9x.

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This plan covers §4 (Docker runtimes) in full, the M4 row of §11, the `docker`, `docker-build-gc`, `ddev`, `aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync`, `browser-mcp` rows of §2 *Per-OS strategies*, the "selected Docker runtime healthy" line of §8, the §0 Rosetta rule for `--vz-rosetta`, and `docs/docker-runtimes.md` from §10. Read the spec before starting. Format exemplars: `docs/superpowers/plans/2026-09-19-macos-m1-engine-core.md` and `docs/superpowers/plans/2026-09-19-macos-m2-shell-dotfiles.md`.

## Global Constraints

- Apple Silicon only; the macOS family id is `"macos"`; Homebrew prefix `/opt/homebrew`. Supported: macOS 27 Golden Gate (primary, this Mac), 26 Tahoe.
- **Every default is free for commercial use** (the Mac does employer and client work). Colima (MIT) is the default runtime. OrbStack and Docker Desktop are opt-in only, and selecting either prints its licence terms (Decisions D3).
- Brew is **never** run with `sudo`. Every brew call goes through `devboost.exec.primitives.pkg`. Service state is read with `brew services info --json <formula>`, never a hard-coded launchd label (Homebrew 7 renamed them `sh.brew.<formula>`; spec §0).
- launchd labels are `dev.devboost.<module-name>` (`launchd.label(name)`). Per-user jobs are LaunchAgents in `~/Library/LaunchAgents` via `launchd.user_agent`. The one root job (the `/var/run/docker.sock` link) is a LaunchDaemon via `launchd.system_daemon`.
- Linux behaviour does not change. Every existing Linux unit text, argv and test stays as it is. The macOS path is reached only through `per_os.macos` + `Module.os_strategy` (the M2 pattern, M2 plan D3).
- Tests are hermetic. `tests/conftest.py`'s autouse `_tmp_home` (HOME and XDG dirs in `tmp_path`) and `_linux_host` (argument-less `osinfo.detect()` returns Fedora) are in force. macOS tests build `Ctx(os=OsInfo("macos", "macos", "aarch64"), ex=<fake>)` explicitly. **No test runs a real `launchctl`, `brew`, `colima`, `orb`, `docker` or `ddev`**: every command goes through `FakeExecutor` or `tests.passstore.fakes.RuleExecutor`, and `launchd.DAEMONS_DIR` / `_docker_colima.DOCKER_SOCK` are redirected into `tmp_path` whenever a test reaches them. `_docker_runtime._sleep` is always monkeypatched; no test sleeps.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy`, `uv run pytest`, all clean. `mypy --strict`, ruff line length ≤ 100.
- Commit messages: Conventional Commits, **no `Co-Authored-By` trailer, no Claude/Anthropic attribution** (constitution). Every commit step below follows this.
- All commands run from `engine/` unless a step says otherwise. Repo-relative paths in `git add` are written from `engine/` (`../docs/...`, `../dotfiles/...`, `../profiles.toml`).
- `KNOWN_GAPS` in `tests/core/test_macos_contract.py`: each task that gives a module a macOS path deletes that name in the same commit. `test_known_gaps_are_still_gaps` fails if you forget.

## Decisions

The spec is silent on these points, or they refine it. The user was not available; each decision is recorded here and carried into the spec in Task 15.

| # | Decision | Why |
|---|---|---|
| D1 | **M4 owns these `KNOWN_GAPS` names:** `docker`, `docker-build-gc`, `ddev`, `ddev-remote`, `data-services`, `aspire`, `aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync`. It also adds one new macOS-only module, `browser-mcp`. `laravel-lsp` (an LSP module) stays with M3/Z2. If M3 already resolved any of the ten (Task 0 checks), the matching step becomes a no-op and M3's version is kept. | The spec's M4 outcome is "ddev, Aspire, data-services", and all of them hang off `docker`. The spec's §2 *Per-OS strategies* table puts the five timer/service modules on `launchd.user_agent`. |
| D2 | **"build-gc" in the M4 row means `docker-build-gc`.** On Linux it is not a timer: it caps BuildKit's cache in `daemon.json`. On macOS it merges the same `builder.gc` block into the **selected runtime's** daemon config (`colima.yaml` `docker:` key, OrbStack `docker.json`, Docker Desktop `~/.docker/daemon.json`) and restarts that engine only when the file changed. No new timer. | Spec §2 lists `docker, docker-build-gc → DockerRuntime (§4)`, and spec §4 has a *Daemon config* row per runtime. |
| D3 | **Colima is the default.** Licensing, checked 2026-09-19: Colima is MIT. OrbStack: "Personal use: free. Business and commercial use: $8/user/mo". Docker Desktop: free only for "a commercial undertaking with fewer than 250 employees and less than US $10,000,000 … in annual revenue" (both conditions). Selecting OrbStack or Docker Desktop logs that sentence as a warning, both at install and on `docker use`. | Spec *Licensing constraints*, re-verified against the vendors' own pages (Sources). |
| D4 | macOS strategies are `per_os = OsMap(macos=<strategy>)`. The module's existing `install`/`verify` start with `if (s := self.os_strategy(ctx)) is not None: …` (M2's `Module.os_strategy`, M2 plan D3). Strategies are small frozen dataclasses in the module's own file. Shared logic is factored into module-level functions that both paths call, and the Linux output stays byte-identical. | This is the pattern M2 establishes. The contract test counts `per_os.macos` as a macOS path. |
| D5 | **Timer mapping.** systemd `OnCalendar=hourly` → launchd `StartCalendarInterval {Minute: 0}`. `OnCalendar=daily` → `{Hour: 0, Minute: 0}`, the same wall-clock times systemd uses. `Persistent=true` ≈ launchd's behaviour for calendar jobs: a run missed while the Mac **slept** happens once on wake. A run missed while it was **powered off** is not caught up; that is the one difference, and it is documented. Each job is `ProgramArguments = ["/bin/sh", "-c", <script>]` (the Linux units already use `/bin/sh -c` for aspire-gc and the vault sync), `EnvironmentVariables.PATH = ~/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`, and stdout/stderr go to `~/Library/Logs/devboost/<name>.log`. `restic` therefore resolves through PATH, never `/usr/bin/restic` (spec §2). The label is `dev.devboost.<module name>`, so the vault job is `dev.devboost.obsidian-sync` and not the Linux unit name `devboost-vault-sync`. | launchd agents start with a bare PATH (`/usr/bin:/bin:/usr/sbin:/sbin`), so `devboost`, `docker` and `restic` would not resolve without it. Console.app shows `~/Library/Logs`. |
| D6 | The M1 `launchd` primitive gains `keep_alive`, `throttle_interval` and `log_path` keyword arguments on `user_agent` (all default `None`, so existing plists are byte-identical), plus `agent_plist(label)`, `agent_installed(ctx, label)` and `remove_daemon(ctx, label)`. | browser-mcp needs `KeepAlive`, and every job needs a log file. Switching away from Colima removes its socket daemon. |
| D7 | **restic-b2 on macOS.** The env file is sourced by `sh`, so on macOS its values are `shlex.quote`d. The Linux `EnvironmentFile` format is unchanged. The job runs `restic init` (failure ignored, like the unit's `ExecStartPre=-`), then `restic backup … && restic forget … --prune`, which matches `ExecStartPost` running only after a successful `ExecStart`. `server._secret` now decrypts through `secrets.age_key(ctx)`, so a key kept in the macOS keychain (M1, `devboost secrets import-key`) works. Off macOS `age_key` yields exactly `key_path()`, so Linux is unchanged. The env file is created `0600` **before** the secrets are written; today it is written first and chmod-ed after. | Parity with the Linux unit, and M1's keychain-held age key would otherwise be invisible to restic-b2. |
| D8 | `restic-backup` is ported **as is**. Like the Linux unit, it expects `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` in the job's environment, and neither systemd `--user` nor launchd provides them. This existing limitation is documented in `docs/docker-runtimes.md` → *Scheduled jobs*, not fixed. `restic-b2` is the configured, working backup. | Fixing it would change Linux behaviour, which is out of scope. |
| D9 | **browser-mcp** becomes a macOS-only engine module (`families = ("macos",)`, profile `remote`, `requires = (Dotfiles,)`, `gui = True`). It is a LaunchAgent running `~/.local/bin/browser-mcp` with `RunAtLoad`, `KeepAlive = {SuccessfulExit: false}` (≈ `Restart=on-failure`) and `ThrottleInterval = 60`, so it retries once a minute while the tailnet is down instead of every 10 s. PATH puts the mise shims first, as the systemd unit does. On Linux the dotfiles keep owning it (systemd unit + `default.target.wants` symlink); M2's `.chezmoiignore` already keeps `.config/systemd` off Darwin. The launcher learns macOS Chrome detection: `[ -d "${CHROME_APP:-/Applications/Google Chrome.app}" ]`. | A dotfile cannot load a launchd job, and `command -v google-chrome` never matches on macOS. `CHROME_APP` also makes the test hermetic. |
| D10 | **Colima's config dir.** Colima 0.10 resolves it at run time: `$COLIMA_HOME` if that directory exists, else `~/.colima` if it exists, else `$XDG_CONFIG_HOME/colima` when XDG is set, else `~/.config/colima` if it exists, else `~/.colima` on macOS (`config/files.go`). M2's `env.sh` sets `XDG_CONFIG_HOME` in shells, but `brew services` starts Colima from launchd with no XDG, so the two could disagree. Before the first `colima` call, devboost therefore creates `$XDG_CONFIG_HOME/colima` (default `~/.config/colima`) unless `~/.colima` or `$COLIMA_HOME` already exists. Every later path (`colima.yaml`, `docker.sock`) comes from `colima_home()`, which mirrors that resolution. **Hand-off to M5:** `timemachine-exclusions` must exclude the resolved Colima home (on a fresh Mac, `~/.config/colima`), not a hard-coded `~/.colima`. | Otherwise shells and the login service would each use their own VM, and any existing `~/.colima` would print "found ~/.colima, ignoring $XDG_CONFIG_HOME" on every command. |
| D11 | **Colima lifecycle.** First run: `colima start --vm-type vz [--vz-rosetta] --mount-type virtiofs --cpu C --memory M --disk 100` creates the VM and saves the flags to `colima.yaml`. Then `colima stop`, then `brew services start colima`. The Homebrew service runs a bare `colima start -f` with `keep_alive successful_exit: true`, so starting it while a VM is already running would loop. The size (`C = max(2, ncpu // 2)`, `M = max(4, ram_gib // 4)`) is applied **only when the VM is created**; later edits to `colima.yaml` are respected. `--dns` is **not** set. DDEV's docs suggest `--dns=1.1.1.1`, but that breaks split-DNS company VPNs; it is listed as a troubleshooting tip instead. `--vz-rosetta` is passed only when `/usr/bin/arch -x86_64 /usr/bin/true` succeeds (spec §0). | The Homebrew formula's service block (Sources). `--vm-type` cannot change after creation (Colima `setFixedConfigs`). |
| D12 | **`colima.yaml` is edited with PyYAML** (new runtime dependency `pyyaml>=6.0.2`; dev dependency `types-PyYAML`). Only the top-level `docker:` mapping is merged; other keys are kept. Comments in `colima.yaml` are lost on the first merge, and this is documented. | The constitution forbids hand-rolled TOML parsing; the same reasoning rules out a hand-rolled YAML editor. Colima itself rewrites the file on `start`. PyInstaller bundles PyYAML's pure-Python path with no extra hook. |
| D13 | **`/var/run/docker.sock` for Colima is a root LaunchDaemon**, `dev.devboost.docker-sock`, which runs `/bin/ln -sf <colima socket> /var/run/docker.sock` at load (`RunAtLoad`). macOS empties `/var/run` at boot, so a one-off `sudo ln` (spec §4) would vanish after a reboot. Switching away from Colima removes the daemon, and removes the link only if it still points at Colima's socket. OrbStack and Docker Desktop manage the link themselves. The Task 16 acceptance run includes a reboot to confirm. | Testcontainers, IDEs and some Aspire integrations ignore docker contexts and use the default socket. |
| D14 | **Docker Desktop settings.** Docker has not documented the keys in `settings-store.json` (docker/docs#23706). devboost therefore updates an **existing** key, matched case-insensitively, and falls back to `Cpus`, `MemoryMiB` and `AutoStart` only when the file has none. A missing `settings-store.json` means the first launch (the Subscription Service Agreement) has not happened, so devboost raises `NeedsUser`. The cask links its own `docker`/`docker-compose` into `/opt/homebrew/bin`, where they clash with Colima's formulae. Installing Docker Desktop therefore runs `brew unlink docker docker-compose` first, and installing Colima while the cask is present runs `brew link --overwrite docker docker-compose`. | This is safer than inventing keys. Brew refuses to overwrite another formula's links. |
| D15 | **OrbStack** is configured with `orb config set cpu <C>`, `memory_mib <M×1024>` and `app.start_at_login true|false`, and started with `orb start`. If any of these fails, the first launch has not been completed (onboarding or licence screen), so devboost raises `NeedsUser` with the fix `open -a OrbStack`. Its daemon config is `~/.orbstack/config/docker.json`, applied with `orb restart docker`. | OrbStack docs (Sources); spec §1 lists the OrbStack/Docker Desktop first-launch screens as `NeedsUser`. |
| D16 | **Runtime selection** is `userconfig.selected_docker_runtime()`. `Settings` gains `docker_runtime: str \| None` (it reads `DEVBOOST_DOCKER_RUNTIME`), and the value is validated in `selected_docker_runtime()`. It is **not** a `Literal` field on `Settings`: `settings = Settings()` runs at import, so a bad env value would crash every command with a pydantic traceback. `UserConfig.docker_runtime` is a validated `Literal`. `userconfig.set_user_value(key, value)` persists the choice with tomli-w. The rewrite drops comments from `config.toml`, which is a small machine-written file. `tests/conftest.py` clears `DEVBOOST_DOCKER_RUNTIME`. | Spec §4 precedence. A developer's exported env var must not leak into tests. |
| D17 | **`devboost docker use <runtime>`** runs on macOS only; elsewhere it fails with `BadParameter`, like `secrets import-key`. `--snapshot/--no-snapshot` controls `ddev snapshot --all`. Without the flag it asks, defaulting to yes; with `--yes` it snapshots. A failed snapshot aborts **before** the old runtime is touched. After the old runtime is stopped, a failure (for example `NeedsUser` for an OrbStack first launch) leaves `config.toml` unchanged and prints `devboost docker use <previous>` as the way back. Choosing the current runtime again re-runs the reconfigure steps (a repair). The re-verify list is `docker`, `docker-build-gc`, `aspire-gc`, `ddev` and `data-services`. The command exits 1 only if `docker` or `docker-build-gc` fails; the other three may legitimately be absent, so they are shown with a `devboost install <name>` hint. | Spec §4 steps 1–5, made safe to re-run. |
| D18 | **ddev on macOS:** `brew install ddev/ddev/ddev` (the tap auto-taps) plus the `mkcert` formula, then `mkcert -install`. If that fails (it needs your password or a keychain approval), devboost raises `NeedsUser`. `ddev-remote` and `data-services` work unchanged on macOS (`ctx.os.headless`, and a bundled compose file with multi-arch images), so they are marked `portable = True`. | DDEV's install docs (Sources); spec §1 `NeedsUser` list. |
| D19 | **Aspire on macOS:** `~/.dotnet/dotnet tool install -g Aspire.Cli` (or `tool update` under `--force`) with `DOTNET_ROOT=~/.dotnet`. The SDK lives in `~/.dotnet` (spec §2 `dotnet-sdk` row, M3), which is not on PATH inside the devboost process. Aspire needs only a Docker CLI with a working context. Colima's VMs resolve `host.docker.internal` (Colima maps it to the host gateway), which Aspire uses for container→dashboard OTLP. | Aspire docs (Sources). |
| D20 | `doctor` gains one macOS check, `docker-runtime`. It is ok when the selected runtime is not installed (detail: `devboost install docker`). It fails when the runtime is installed but its engine does not answer on its context. With Colima and no Rosetta, the detail adds the qemu slowdown note (spec §0). | Spec §8. |
| D21 | `Docker` adds `requires = (Homebrew,)` and `after = (Rosetta,)`, both M3 module classes. `Homebrew` is `families = ("macos",)`, so Linux plans drop it, as `Flatpak` is dropped on Arch. `after` only orders modules; it never pulls Rosetta into a plan. | Spec §1 *Ordering*. The Rosetta check must see Rosetta when both are in the plan. |
| D22 | M4 does not edit the `macos = […]` line of `profiles.toml` (M3 expands it). Its only profile edit is `remote += browser-mcp`. | Avoids a conflict with M3. |

**Not pre-validated.** Unlike M2, these snippets were written against `main` @ `655be95` plus the M2 plan's published interfaces (`BrewFormula`, `BrewCask`, `Module.os_strategy`, the `plan._supported` fallback). They have not been run. If a snippet fails, first suspect drift from M2/M3/P2 (Task 0), then the snippet.

## Depends on M1, M2 (landed) and M3 (assumed)

M1 and M2 are merged before M4 executes. M4 consumes:

- **M1:** `exec/primitives/launchd.py` (`label`, `user_agent`, `system_daemon`, `agent_loaded`, `remove_agent`, `DAEMONS_DIR`); `pkg.Brew`, `pkg.install_cask`, `pkg.cask_installed`, `pkg.BREW_ENV`, `pkg._brew_or_raise`; `NeedsUser`, `PresentUnmanaged`; `secrets.age_key`; `cli/host.py` `mac_session`; `cli/doctor.py` macOS branch.
- **M2:** `devboost.modules._brew.BrewFormula` / `BrewCask`; `Module.os_strategy(ctx) -> Installer | None`; `plan._supported`, which treats a module's own `install()` as the fallback on OSes its `per_os` does not name; `.chezmoiignore` ignoring `.config/systemd` on Darwin; `env.sh` exporting `XDG_CONFIG_HOME=$HOME/.config` on Darwin.

**M3 + Z2 (the catalog) is planned in parallel, and its plan had not been pushed when this plan was written.** M4 assumes M3 delivers spec §2, and in particular the list below. Task 0 checks each item and records the real names. Every later task uses those recorded names.

| # | Assumption about M3 | Where M4 uses it | Task 0 check |
|---|---|---|---|
| A1 | A `homebrew` module class exists, with `name = "homebrew"` and `families = ("macos",)`. This plan imports it as `from devboost.modules.macos_base import Homebrew`. | `Docker.requires` (D21) | `grep -rn 'name = "homebrew"' src/devboost/modules` |
| A2 | A `rosetta` module class exists, with `name = "rosetta"` and `families = ("macos",)`, imported the same way as A1. | `Docker.after` (D21) | `grep -rn 'name = "rosetta"' src/devboost/modules` |
| A3 | `dotnet-sdk`'s macOS strategy installs .NET 10 into `~/.dotnet` with `dotnet-install.sh` (spec §2). | `_MacAspire` (D19) | `grep -n 'dotnet-install' src/devboost/modules/dev_stacks.py` |
| A4 | M3 expands `macos = [...]` in `profiles.toml` to the spec's list, which includes `base`, `laravel`, `dotnet`, `data`, `dev-hygiene`, `remote` and `apps`. M4 does not touch that line (D22). | Acceptance (Task 16) | `grep -n '^macos' ../profiles.toml` |
| A5 | The `tailscale` macOS strategy symlinks the app's CLI to `~/.local/bin/tailscale` (spec §2). | browser-mcp launcher (`tailscale ip -4`) | `grep -n 'local/bin' src/devboost/modules/server.py` |
| A6 | `obsidian` (cask), `secrets` and `ssh-setup` have macOS paths. | `obsidian-sync` requires them | They are absent from `KNOWN_GAPS` |
| A7 | M3 does **not** edit `Docker`, `DockerBuildCacheGc`, `Ddev`, `DdevRemote`, `DataServices`, `Aspire`, `AspireGc`, `ResticBackup`, `ResticB2` or `ObsidianSync`. If it did (spec §2 also lists `ddev` in the per-OS table), keep M3's code for that module and skip M4's step for it. | Tasks 7–10 | `git log origin/main --oneline -- src/devboost/modules/{docker,ddev,dev_hygiene,system,server,apps,dev_stacks}.py` |
| A8 | `PackageModule`/`FlatpakApp` add `Homebrew` to `requires` on their own (spec §1). M4 adds it only to its custom modules. | — | `grep -n 'Homebrew' src/devboost/modules/_pkgmodule.py` |

**Parallel P2 (pass on macOS)** may also edit `exec/primitives/launchd.py` (the pass-sync agent). **Parallel M5** owns `timemachine-exclusions`, and D10 hands the Colima-home rule to it. Task 0 checks both.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/exec/primitives/launchd.py` (modify) | `keep_alive`/`throttle_interval`/`log_path`; `agent_plist`, `agent_installed`, `remove_daemon` | 1 |
| `engine/src/devboost/exec/primitives/pkg.py` (modify) | `brew_services`, `service_running`, `brew_link`, `brew_unlink` | 2 |
| `engine/src/devboost/core/userconfig.py`, `core/settings.py`, `engine/tests/conftest.py` (modify) | runtime name type, `selected_docker_runtime`, `set_user_value`; env field; hermetic env | 3 |
| `engine/src/devboost/modules/_docker_runtime.py` (create) | `DockerRuntime` protocol, VM sizing, Rosetta probe, context/engine helpers, licence notes; later `runtime_for`/`selected_runtime` | 4, 7 |
| `engine/src/devboost/modules/_docker_colima.py` (create); `engine/pyproject.toml`, `engine/uv.lock` (modify) | Colima runtime; PyYAML | 5 |
| `engine/src/devboost/modules/_docker_orbstack.py`, `_docker_desktop.py` (create) | OrbStack and Docker Desktop runtimes | 6 |
| `engine/src/devboost/modules/docker.py` (modify) | macOS strategies for `docker`, `docker-build-gc`; `BUILDER_GC` public | 7 |
| `engine/src/devboost/modules/ddev.py`, `dev_stacks.py` (modify) | ddev macOS strategy; `ddev-remote`/`data-services` portable; Aspire macOS strategy | 8 |
| `engine/src/devboost/modules/_launchd_jobs.py` (create); `dev_hygiene.py`, `system.py` (modify) | `LaunchdTimer`; aspire-gc, restic-backup | 9 |
| `engine/src/devboost/modules/server.py`, `apps.py` (modify) | restic-b2 and obsidian-sync macOS strategies; shared helpers | 10 |
| `engine/src/devboost/modules/browser_mcp.py` (create); `dotfiles/dot_local/bin/executable_browser-mcp`, `profiles.toml` (modify) | browser-mcp agent; Chrome detection; `remote` profile | 11 |
| `engine/src/devboost/modules/_docker_switch.py`, `engine/src/devboost/cli/docker_cmd.py` (create); `cli/app.py` (modify) | `devboost docker use` | 12 |
| `engine/src/devboost/cli/doctor.py` (modify) | `docker-runtime` check | 13 |
| `engine/tests/core/test_macos_m4_plan.py` (create) | the M4 set plans cleanly on macOS and on Fedora | 14 |
| `docs/docker-runtimes.md` (create); `docs/macos.md`, `docs/obsidian-sync.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `dotfiles/dot_config/systemd/user/README.md`, `README.md`, `CHANGELOG.md`, spec (modify) | docs | 15 |

Tests created: `tests/primitives/test_launchd.py` (extend), `tests/primitives/test_pkg_brew_services.py`, `tests/core/test_docker_pref.py`, `tests/modules/test_docker_runtime.py`, `tests/modules/test_docker_colima.py`, `tests/modules/test_docker_orbstack_desktop.py`, `tests/modules/test_docker_macos.py`, `tests/modules/test_ddev_aspire_macos.py`, `tests/modules/test_launchd_jobs.py`, `tests/modules/test_backup_vault_macos.py`, `tests/modules/test_browser_mcp.py`, `tests/dotfiles/test_browser_mcp_launcher.py`, `tests/modules/test_docker_switch.py`, `tests/cli/test_docker_cmd.py`, `tests/cli/test_doctor_docker.py`, `tests/core/test_macos_m4_plan.py`.

---
### Task 0: Branch, baseline, shared-file re-check against main + M2 + M3

M1, P1, Z1, M2 and M3 are on `main` when this runs; P2 and M5 may have merged too. This task records what they changed in the files M4 edits, so every later task merges onto that state instead of overwriting it.

**Files:** none (environment only)

- [ ] **Step 1: Branch from the current main** (repo root)

```bash
git fetch origin
git checkout -b feat/macos-m4-docker origin/main
```

- [ ] **Step 2: Baseline gate** (from `engine/`)

```bash
cd engine && uv sync
uv run ruff check && uv run mypy && uv run pytest 2>&1 | tail -3
```
Expected: all green. If anything is red on a clean `main`, stop and report it. M4 must start green.

- [ ] **Step 3: Confirm the M1/M2 interfaces M4 consumes**

```bash
grep -n '^def \|^DAEMONS_DIR' src/devboost/exec/primitives/launchd.py
grep -n '^def install_cask\|^def cask_installed\|^def _brew_or_raise\|^BREW_ENV' src/devboost/exec/primitives/pkg.py
grep -n 'class BrewFormula\|class BrewCask' src/devboost/modules/_brew.py
grep -n 'def os_strategy' src/devboost/model.py
grep -n 'XDG_CONFIG_HOME' ../dotfiles/dot_config/devboost/env.sh
grep -n 'systemd' ../dotfiles/.chezmoiignore
```
Expected: every grep prints at least one line. `launchd.py` has `label`, `user_agent`, `system_daemon`, `agent_loaded`, `daemon_loaded`, `remove_agent`. If P2 already added `keep_alive`/`log_path`-style parameters, or `agent_plist`/`remove_daemon`, write that down. Task 1 then adds only what is still missing, keeping P2's names wherever they are the same concept.

- [ ] **Step 4: Resolve the M3 assumptions (A1–A8)**

```bash
grep -rn 'name = "homebrew"\|name = "rosetta"' src/devboost/modules
grep -n 'dotnet-install' src/devboost/modules/dev_stacks.py
grep -n '^macos\|^remote' ../profiles.toml
grep -n 'local/bin' src/devboost/modules/server.py
git log origin/main --oneline -- src/devboost/modules/docker.py src/devboost/modules/ddev.py \
  src/devboost/modules/dev_hygiene.py src/devboost/modules/system.py \
  src/devboost/modules/server.py src/devboost/modules/apps.py src/devboost/modules/dev_stacks.py
sed -n '/^KNOWN_GAPS/,/^})/p' tests/core/test_macos_contract.py | grep -E '"(docker|docker-build-gc|ddev|ddev-remote|data-services|aspire|aspire-gc|restic-backup|restic-b2|obsidian-sync|obsidian|secrets|ssh-setup)"'
```

Write down:

- **A1/A2:** the module file that defines `Homebrew` and `Rosetta`. This plan writes `from devboost.modules.macos_base import Homebrew, Rosetta`. If the real module is, say, `devboost.modules.macos`, use that path in Task 7 Step 3. That is the only place the import appears.
- **A3:** the `dotnet-sdk` macOS strategy uses `~/.dotnet`. If M3 instead put `dotnet` on the executor's PATH **and** removed `aspire` from `KNOWN_GAPS`, skip Task 8's Aspire step.
- **A4:** the `macos` line lists the spec's profiles. `remote` is `["tailscale","mosh"]`, or whatever M3 left it as. Task 11 appends `"browser-mcp"` to the line as it is.
- **A7:** for each M4 module file M3 touched, read M3's diff. If M3 already gave a module a macOS path, skip M4's step for that module and do not remove its name from `KNOWN_GAPS` again.
- **KNOWN_GAPS:** the grep lists which M4-owned names are still gaps. Those are exactly the ones Tasks 7–10 remove. `obsidian`, `secrets` and `ssh-setup` must be **absent** (A6).

- [ ] **Step 5: Parallel work check (P2, M5)**

```bash
git log origin/main --oneline -- src/devboost/exec/primitives/launchd.py src/devboost/passstore/sync.py
grep -rn 'colima' src/devboost/modules | grep -v _docker_
```
If P2 changed `launchd.py`, re-read it before Task 1. If M5's `timemachine-exclusions` hard-codes `~/.colima`, note it in the PR description (D10 hand-off). Do not edit M5's module.

No commit.

---

### Task 1: launchd primitive — KeepAlive, ThrottleInterval, log files, `agent_installed`, `remove_daemon`

**Files:**
- Modify: `engine/src/devboost/exec/primitives/launchd.py`
- Test: `engine/tests/primitives/test_launchd.py` (extend)

**Interfaces:**
- Consumes: M1 `launchd` as it is (Task 0 Step 3).
- Produces:
  - `launchd.user_agent(ctx, lbl, program_args, *, start_interval=None, start_calendar=None, run_at_load=False, env=None, keep_alive: bool | Mapping[str, bool] | None = None, throttle_interval: int | None = None, log_path: Path | None = None) -> bool`. A `log_path` sets both `StandardOutPath` and `StandardErrorPath` and creates the log's parent directory.
  - `launchd.agent_plist(lbl: str) -> Path`: `~/Library/LaunchAgents/<lbl>.plist`.
  - `launchd.agent_installed(ctx, lbl) -> bool`: the plist exists **and** `launchctl print` succeeds.
  - `launchd.remove_daemon(ctx, lbl) -> None`: `sudo launchctl bootout system/<lbl>` (not-loaded is ignored), then `sudo rm -f <DAEMONS_DIR>/<lbl>.plist`.

- [ ] **Step 1: Write the failing tests** (append to `tests/primitives/test_launchd.py`)

```python
def test_user_agent_keep_alive_throttle_and_log(home: Path) -> None:
    log = home / "Library" / "Logs" / "devboost" / "x.log"
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x", ["/bin/echo"],
        run_at_load=True, keep_alive={"SuccessfulExit": False},
        throttle_interval=60, log_path=log,
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.x.plist").read_bytes())
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 60
    assert data["StandardOutPath"] == str(log)
    assert data["StandardErrorPath"] == str(log)
    assert log.parent.is_dir()


def test_user_agent_keep_alive_true(home: Path) -> None:
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.k", ["/bin/echo"], keep_alive=True
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.k.plist").read_bytes())
    assert data["KeepAlive"] is True


def test_user_agent_without_new_options_has_no_new_keys(home: Path) -> None:
    launchd.user_agent(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.p", ["/bin/echo"])
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.p.plist").read_bytes())
    assert data == {"Label": "dev.devboost.p", "ProgramArguments": ["/bin/echo"]}


def test_agent_plist_and_agent_installed(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert launchd.agent_installed(ctx, "dev.devboost.x") is False  # no plist yet
    launchd.user_agent(ctx, "dev.devboost.x", ["/bin/echo"])
    assert launchd.agent_plist("dev.devboost.x") == (
        home / "Library" / "LaunchAgents" / "dev.devboost.x.plist"
    )
    assert launchd.agent_installed(ctx, "dev.devboost.x") is True
    unloaded = Ctx(os=MAC, ex=FakeExecutor(scripts={"launchctl": Result(113)}))
    assert launchd.agent_installed(unloaded, "dev.devboost.x") is False


def test_remove_daemon_bootouts_and_deletes_with_sudo(home: Path) -> None:
    ex = FakeExecutor()
    launchd.remove_daemon(Ctx(os=MAC, ex=ex), "dev.devboost.docker-sock")
    assert ex.calls == [
        ["sudo", "launchctl", "bootout", "system/dev.devboost.docker-sock"],
        ["sudo", "rm", "-f", str(home / "LaunchDaemons" / "dev.devboost.docker-sock.plist")],
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/primitives/test_launchd.py -v`
Expected: the five new tests FAIL (`TypeError: user_agent() got an unexpected keyword argument 'keep_alive'` and `AttributeError: … 'agent_plist'`/`'remove_daemon'`). The existing tests still PASS.

- [ ] **Step 3: Implement** (`engine/src/devboost/exec/primitives/launchd.py`)

Replace `_plist` with:

```python
def _plist(
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None,
    start_calendar: Mapping[str, int] | None,
    run_at_load: bool,
    env: Mapping[str, str] | None,
    keep_alive: bool | Mapping[str, bool] | None = None,
    throttle_interval: int | None = None,
    log_path: Path | None = None,
) -> bytes:
    data: dict[str, Any] = {"Label": lbl, "ProgramArguments": list(program_args)}
    if start_interval is not None:
        data["StartInterval"] = start_interval
    if start_calendar is not None:
        data["StartCalendarInterval"] = dict(start_calendar)
    if run_at_load:
        data["RunAtLoad"] = True
    if env:
        data["EnvironmentVariables"] = dict(env)
    if keep_alive is not None:
        data["KeepAlive"] = keep_alive if isinstance(keep_alive, bool) else dict(keep_alive)
    if throttle_interval is not None:
        data["ThrottleInterval"] = throttle_interval
    if log_path is not None:
        data["StandardOutPath"] = str(log_path)
        data["StandardErrorPath"] = str(log_path)
    return plistlib.dumps(data)
```

Add below `daemon_loaded`:

```python
def agent_plist(lbl: str) -> Path:
    """Where the per-user agent's plist lives."""
    return _agents_dir() / f"{lbl}.plist"


def agent_installed(ctx: Ctx, lbl: str) -> bool:
    """The agent's plist is on disk and launchd has it loaded."""
    return agent_plist(lbl).exists() and agent_loaded(ctx, lbl)
```

Replace `user_agent` with:

```python
def user_agent(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
    keep_alive: bool | Mapping[str, bool] | None = None,
    throttle_interval: int | None = None,
    log_path: Path | None = None,
) -> bool:
    """Install/refresh a per-user LaunchAgent. Returns True when anything changed.

    ``keep_alive`` is launchd's ``KeepAlive`` (``True``, or e.g. ``{"SuccessfulExit":
    False}`` — restart only after a failure, like systemd's ``Restart=on-failure``).
    ``log_path`` receives both stdout and stderr; its directory is created.
    """
    path = agent_plist(lbl)
    body = _plist(
        lbl,
        program_args,
        start_interval=start_interval,
        start_calendar=start_calendar,
        run_at_load=run_at_load,
        env=env,
        keep_alive=keep_alive,
        throttle_interval=throttle_interval,
        log_path=log_path,
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    ctx.ex.run(["launchctl", "bootout", f"{_gui_domain()}/{lbl}"])  # not loaded → ignored
    res = ctx.ex.run(["launchctl", "bootstrap", _gui_domain(), str(path)])
    if not res.ok:
        raise InstallError(
            "launchd", f"launchctl bootstrap {_gui_domain()} {path}", res.code
        )
    return True
```

Append at the end of the file:

```python
def remove_daemon(ctx: Ctx, lbl: str) -> None:
    """Unload and delete a root LaunchDaemon (a missing one is not an error)."""
    ctx.ex.run(["launchctl", "bootout", f"system/{lbl}"], sudo=True)
    ctx.ex.run(["rm", "-f", str(DAEMONS_DIR / f"{lbl}.plist")], sudo=True)
```

`remove_agent` now calls `agent_plist(lbl).unlink(missing_ok=True)` instead of building the path inline.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/primitives/test_launchd.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/primitives/launchd.py tests/primitives/test_launchd.py
git commit -m "feat(launchd): KeepAlive, throttle, log files, agent_installed and remove_daemon"
```

---

### Task 2: pkg — `brew services` and link helpers

**Files:**
- Modify: `engine/src/devboost/exec/primitives/pkg.py`
- Test: `engine/tests/primitives/test_pkg_brew_services.py` (create)

**Interfaces:**
- Consumes: `pkg._brew_or_raise`, `Brew._brew` (M1).
- Produces:
  - `BrewServiceVerb = Literal["start", "stop", "restart"]`
  - `pkg.brew_services(ctx, verb: BrewServiceVerb, formula: str) -> Result`: never raises on a non-zero exit (stopping a service that is not running fails harmlessly). Raises `UnsupportedOS` off macOS.
  - `pkg.service_running(ctx, formula: str) -> bool`: parses `brew services info --json <formula>`; any error means `False`.
  - `pkg.brew_link(ctx, *formulae: str, overwrite: bool = False) -> Result`, `pkg.brew_unlink(ctx, *formulae: str) -> Result`.

- [ ] **Step 1: Write the failing tests** (`tests/primitives/test_pkg_brew_services.py`)

```python
from __future__ import annotations

import json

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import Ctx
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_brew_services_argv_and_env() -> None:
    ex = RuleExecutor()
    assert pkg.brew_services(Ctx(os=MAC, ex=ex), "start", "colima").ok
    assert ex.calls == [["brew", "services", "start", "colima"]]
    assert ex.envs[0] == pkg.BREW_ENV


def test_brew_services_returns_failure_without_raising() -> None:
    ex = RuleExecutor(rules=[(("services",), Result(1))])
    assert pkg.brew_services(Ctx(os=MAC, ex=ex), "stop", "colima").ok is False


def test_service_running_reads_brew_json() -> None:
    running = json.dumps([{"name": "colima", "running": True, "loaded": True}])
    ex = RuleExecutor(rules=[(("info", "--json"), Result(0, stdout=running))])
    assert pkg.service_running(Ctx(os=MAC, ex=ex), "colima") is True
    assert ex.calls == [["brew", "services", "info", "--json", "colima"]]


@pytest.mark.parametrize(
    ("stdout", "code"),
    [
        (json.dumps([{"name": "colima", "running": False}]), 0),
        (json.dumps([{"name": "other", "running": True}]), 0),
        ("not json", 0),
        ("", 1),
    ],
)
def test_service_not_running(stdout: str, code: int) -> None:
    ex = RuleExecutor(rules=[(("info",), Result(code, stdout=stdout))])
    assert pkg.service_running(Ctx(os=MAC, ex=ex), "colima") is False


def test_link_and_unlink_argv() -> None:
    ex = RuleExecutor()
    ctx = Ctx(os=MAC, ex=ex)
    pkg.brew_link(ctx, "docker", "docker-compose", overwrite=True)
    pkg.brew_unlink(ctx, "docker")
    pkg.brew_link(ctx, "docker")
    assert ex.calls == [
        ["brew", "link", "--overwrite", "docker", "docker-compose"],
        ["brew", "unlink", "docker"],
        ["brew", "link", "docker"],
    ]


def test_service_helpers_refuse_off_macos() -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    with pytest.raises(UnsupportedOS):
        pkg.brew_services(ctx, "start", "colima")
    with pytest.raises(UnsupportedOS):
        pkg.service_running(ctx, "colima")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/primitives/test_pkg_brew_services.py -v`
Expected: FAIL with `AttributeError: module 'devboost.exec.primitives.pkg' has no attribute 'brew_services'`.

- [ ] **Step 3: Implement** (`engine/src/devboost/exec/primitives/pkg.py`)

Add `import json` next to `import re`, and change `from typing import Protocol, runtime_checkable` to `from typing import Literal, Protocol, runtime_checkable`. Append after `upgrade`:

```python
BrewServiceVerb = Literal["start", "stop", "restart"]


def brew_services(ctx: Ctx, verb: BrewServiceVerb, formula: str) -> Result:
    """`brew services <verb> <formula>` (macOS). The result is returned, not raised on:
    stopping a service that is not running fails harmlessly, so the caller decides."""
    return _brew_or_raise(ctx, "brew services")._brew(ctx, "services", verb, formula)


def service_running(ctx: Ctx, formula: str) -> bool:
    """True when Homebrew reports the formula's service running.

    Reads ``brew services info --json`` — never a launchd label, which Homebrew 7 renamed
    to ``sh.brew.<formula>`` (spec §0).
    """
    res = _brew_or_raise(ctx, "brew services")._brew(
        ctx, "services", "info", "--json", formula
    )
    if not res.ok:
        return False
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return False
    entries = data if isinstance(data, list) else [data]
    return any(
        isinstance(e, dict) and e.get("name") == formula and e.get("running") is True
        for e in entries
    )


def brew_link(ctx: Ctx, *formulae: str, overwrite: bool = False) -> Result:
    """`brew link [--overwrite] <formulae>` — take a binary name back from a cask."""
    args = ["link", *(["--overwrite"] if overwrite else []), *formulae]
    return _brew_or_raise(ctx, "brew link")._brew(ctx, *args)


def brew_unlink(ctx: Ctx, *formulae: str) -> Result:
    """`brew unlink <formulae>` — free a binary name for a cask that ships its own."""
    return _brew_or_raise(ctx, "brew unlink")._brew(ctx, "unlink", *formulae)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/primitives/ -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/primitives/pkg.py tests/primitives/test_pkg_brew_services.py
git commit -m "feat(pkg): brew services state and link/unlink helpers"
```

---

### Task 3: Runtime preference — `selected_docker_runtime`, `set_user_value`

**Files:**
- Modify: `engine/src/devboost/core/userconfig.py`, `engine/src/devboost/core/settings.py`, `engine/tests/conftest.py`
- Test: `engine/tests/core/test_docker_pref.py` (create)

**Interfaces:**
- Produces (all in `devboost.core.userconfig`):
  - `DockerRuntimeName = Literal["colima", "orbstack", "docker-desktop"]`
  - `DOCKER_RUNTIMES: tuple[DockerRuntimeName, ...]`, `DEFAULT_DOCKER_RUNTIME: DockerRuntimeName = "colima"`
  - `UserConfig.docker_runtime: DockerRuntimeName | None = None`
  - `parse_docker_runtime(value: str) -> DockerRuntimeName`: raises `ConfigError("unknown docker runtime 'x' (expected one of: colima, orbstack, docker-desktop)")`.
  - `selected_docker_runtime(path: Path | None = None) -> DockerRuntimeName`: `DEVBOOST_DOCKER_RUNTIME` > config file > `"colima"`.
  - `set_user_value(key: str, value: str, path: Path | None = None) -> None`: read-modify-write of `config.toml`. The result is validated against `UserConfig` before it is written, and the file is replaced atomically.
- `Settings.docker_runtime: str | None = None` (env `DEVBOOST_DOCKER_RUNTIME`, validated by `selected_docker_runtime`; D16).

- [ ] **Step 1: Make the tests hermetic for the new env var** (`tests/conftest.py`, inside `_tmp_home`, after the `MISE_DATA_DIR` line)

```python
    monkeypatch.delenv("DEVBOOST_DOCKER_RUNTIME", raising=False)
```

- [ ] **Step 2: Write the failing tests** (`tests/core/test_docker_pref.py`)

```python
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.userconfig import (
    DOCKER_RUNTIMES,
    config_path,
    load_user_config,
    parse_docker_runtime,
    selected_docker_runtime,
    set_user_value,
)


def test_runtime_names() -> None:
    assert DOCKER_RUNTIMES == ("colima", "orbstack", "docker-desktop")


def test_default_is_colima() -> None:
    assert selected_docker_runtime() == "colima"


def test_config_file_beats_the_default(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "orbstack"\n', encoding="utf-8")
    assert selected_docker_runtime(cfg) == "orbstack"


def test_env_beats_the_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "orbstack"\n', encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "docker-desktop")
    assert selected_docker_runtime(cfg) == "docker-desktop"


def test_bad_env_value_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "podman")
    with pytest.raises(ConfigError, match="unknown docker runtime 'podman'"):
        selected_docker_runtime()


def test_bad_config_value_is_a_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "podman"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="docker_runtime"):
        load_user_config(cfg)


def test_parse_accepts_every_runtime() -> None:
    for name in DOCKER_RUNTIMES:
        assert parse_docker_runtime(name) == name


def test_set_user_value_keeps_other_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "devboost" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('pass_repo = "me/store"\n', encoding="utf-8")
    set_user_value("docker_runtime", "orbstack", cfg)
    assert tomllib.loads(cfg.read_text(encoding="utf-8")) == {
        "pass_repo": "me/store",
        "docker_runtime": "orbstack",
    }
    assert [p.name for p in cfg.parent.iterdir()] == ["config.toml"]  # no temp file left


def test_set_user_value_refuses_an_invalid_value(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    with pytest.raises(ConfigError, match="docker_runtime"):
        set_user_value("docker_runtime", "podman", cfg)
    assert not cfg.exists()


def test_set_user_value_defaults_to_the_xdg_config_file() -> None:
    set_user_value("docker_runtime", "colima")
    assert load_user_config(config_path()).docker_runtime == "colima"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/core/test_docker_pref.py -v`
Expected: FAIL with `ImportError: cannot import name 'DOCKER_RUNTIMES'`.

- [ ] **Step 4: Implement**

`core/settings.py`: add the field under `root`:

```python
    #: DEVBOOST_DOCKER_RUNTIME — deliberately a plain str: `settings = Settings()` runs at
    #: import, so a Literal here would turn a typo into a traceback on every command.
    #: userconfig.selected_docker_runtime() validates it.
    docker_runtime: str | None = None
```

`core/userconfig.py`: the imports become

```python
import os
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core.errors import ConfigError
from devboost.core.settings import Settings
```

Add below `DEFAULT_PASS_REPO`:

```python
DockerRuntimeName = Literal["colima", "orbstack", "docker-desktop"]
DOCKER_RUNTIMES: tuple[DockerRuntimeName, ...] = ("colima", "orbstack", "docker-desktop")
DEFAULT_DOCKER_RUNTIME: DockerRuntimeName = "colima"
_RUNTIME_BY_NAME: dict[str, DockerRuntimeName] = {n: n for n in DOCKER_RUNTIMES}
```

Add the field to `UserConfig`:

```python
    docker_runtime: DockerRuntimeName | None = None
```

Append:

```python
def parse_docker_runtime(value: str) -> DockerRuntimeName:
    """The runtime named by ``value``, or a ConfigError listing the valid names."""
    name = _RUNTIME_BY_NAME.get(value)
    if name is None:
        raise ConfigError(
            f"unknown docker runtime {value!r} "
            f"(expected one of: {', '.join(DOCKER_RUNTIMES)})"
        )
    return name


def selected_docker_runtime(path: Path | None = None) -> DockerRuntimeName:
    """DEVBOOST_DOCKER_RUNTIME > ``docker_runtime`` in config.toml > colima (spec §4)."""
    env = Settings().docker_runtime
    if env:
        return parse_docker_runtime(env)
    return load_user_config(path).docker_runtime or DEFAULT_DOCKER_RUNTIME


def set_user_value(key: str, value: str, path: Path | None = None) -> None:
    """Set one key in config.toml, keeping the others. Refuses to write an invalid file.

    The file is rewritten with tomli-w, so comments in it are not preserved.
    """
    p = path if path is not None else config_path()
    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{p}: invalid TOML ({exc})") from exc
    data[key] = value
    try:
        UserConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{p}: invalid value for {key}") from exc
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
    tmp.replace(p)
```

(`os` is already imported for `config_path`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/core/ -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. `tests/core/test_userconfig.py` still passes: the new field is optional.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/core/userconfig.py src/devboost/core/settings.py \
  tests/conftest.py tests/core/test_docker_pref.py
git commit -m "feat(config): docker runtime preference and set_user_value"
```

---

### Task 4: `_docker_runtime.py` — the protocol and the shared helpers

**Files:**
- Create: `engine/src/devboost/modules/_docker_runtime.py`
- Test: `engine/tests/modules/test_docker_runtime.py` (create)

**Interfaces:**
- Consumes: `DockerRuntimeName` (Task 3).
- Produces (module `devboost.modules._docker_runtime`):
  - `class DockerRuntime(Protocol)` with read-only `name: DockerRuntimeName`, `context_name: str`, and the methods `daemon_config_path() -> Path`, `installed(ctx) -> bool`, `install(ctx) -> None`, `configure(ctx) -> None`, `start(ctx) -> None`, `stop(ctx) -> None`, `disable_autostart(ctx) -> None`, `release_socket(ctx) -> None`, `merge_daemon_config(ctx, patch: Mapping[str, Any]) -> bool`, `daemon_config_has(patch: Mapping[str, Any]) -> bool`, `restart_engine(ctx) -> None`, `verify(ctx) -> bool`. `configure` runs after `install` and before `start`. `release_socket` undoes anything the runtime did to `/var/run/docker.sock`.
  - `@dataclass(frozen=True) class VmSize: cpu: int; memory_gib: int` and `vm_size(ctx) -> VmSize`: `cpu = max(2, ncpu // 2)`, `memory_gib = max(4, ram_gib // 4)` from `sysctl -n hw.ncpu` / `hw.memsize`. If sysctl fails, it assumes 4 CPUs and 16 GiB.
  - `rosetta_present(ctx) -> bool`: `/usr/bin/arch -x86_64 /usr/bin/true` succeeds.
  - `current_context(ctx) -> str`, `use_context(ctx, name) -> None` (raises `InstallError`), `engine_up(ctx, context) -> bool`, `engine_verified(ctx, context) -> bool` (the current context is `context` **and** the engine answers on it).
  - `wait_for_engine(ctx, context, *, timeout: float = ENGINE_TIMEOUT, interval: float = 3.0) -> None`: raises `InstallError("docker", "docker --context <c> info", 1)` on timeout. The test seams are the module attributes `_sleep` and `_clock`.
  - `docker_config_path() -> Path` (`$DOCKER_CONFIG/config.json`, default `~/.docker/config.json`), `read_json(path) -> dict[str, Any]` (a missing, invalid or non-object file gives `{}`), `json_has(path, patch) -> bool`.
  - `license_note(name: DockerRuntimeName) -> str | None`.

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_docker_runtime.py`)

```python
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _docker_runtime as rt
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def test_vm_size_is_half_the_cpus_and_a_quarter_of_the_ram() -> None:
    ctx = _ctx(
        (("hw.ncpu",), Result(0, stdout="11\n")),
        (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
    )
    assert rt.vm_size(ctx) == rt.VmSize(cpu=5, memory_gib=6)


def test_vm_size_floors() -> None:
    ctx = _ctx(
        (("hw.ncpu",), Result(0, stdout="2\n")),
        (("hw.memsize",), Result(0, stdout=f"{8 * GIB}\n")),
    )
    assert rt.vm_size(ctx) == rt.VmSize(cpu=2, memory_gib=4)


def test_vm_size_defaults_when_sysctl_fails() -> None:
    assert rt.vm_size(_ctx((("sysctl",), Result(1)))) == rt.VmSize(cpu=2, memory_gib=4)


def test_rosetta_probe() -> None:
    ctx = _ctx()
    assert rt.rosetta_present(ctx) is True
    assert ctx.ex.calls == [["/usr/bin/arch", "-x86_64", "/usr/bin/true"]]  # type: ignore[attr-defined]
    assert rt.rosetta_present(_ctx((("-x86_64",), Result(1)))) is False


def test_use_context() -> None:
    ctx = _ctx()
    rt.use_context(ctx, "colima")
    assert ctx.ex.calls == [["docker", "context", "use", "colima"]]  # type: ignore[attr-defined]
    with pytest.raises(InstallError, match="docker context use colima"):
        rt.use_context(_ctx((("context", "use"), Result(1))), "colima")


def test_engine_verified_needs_the_context_and_a_live_engine() -> None:
    show = (("context", "show"), Result(0, stdout="colima\n"))
    assert rt.engine_verified(_ctx(show), "colima") is True
    assert rt.engine_verified(_ctx(show), "orbstack") is False
    assert rt.engine_verified(_ctx(show, (("info",), Result(1))), "colima") is False
    assert rt.current_context(_ctx((("context", "show"), Result(1)))) == ""


def test_engine_up_argv() -> None:
    ctx = _ctx()
    assert rt.engine_up(ctx, "colima") is True
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["docker", "--context", "colima", "info", "--format", "{{.ServerVersion}}"]
    ]


class _Flaky(RuleExecutor):
    """`docker … info` fails ``fails`` times, then succeeds."""

    def __init__(self, fails: int) -> None:
        super().__init__()
        self.fails = fails

    def run(self, argv, **kw):  # type: ignore[no-untyped-def, override]
        res = super().run(argv, **kw)
        if "info" in argv and self.fails > 0:
            self.fails -= 1
            return Result(1)
        return res


def test_wait_for_engine_polls_until_up(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(rt, "_sleep", sleeps.append)
    monkeypatch.setattr(rt, "_clock", lambda: 0.0)
    rt.wait_for_engine(Ctx(os=MAC, ex=_Flaky(2)), "colima", interval=2.0)
    assert sleeps == [2.0, 2.0]


def test_wait_for_engine_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: Iterator[float] = iter([0.0, 1.0, 999.0])
    monkeypatch.setattr(rt, "_sleep", lambda s: None)
    monkeypatch.setattr(rt, "_clock", lambda: next(ticks))
    with pytest.raises(InstallError, match="docker --context colima info"):
        rt.wait_for_engine(Ctx(os=MAC, ex=_Flaky(99)), "colima", timeout=180.0)


def test_docker_config_path_honours_docker_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert rt.docker_config_path() == tmp_path / ".docker" / "config.json"
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "dc"))
    assert rt.docker_config_path() == tmp_path / "dc" / "config.json"


def test_read_json_and_json_has(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    assert rt.read_json(p) == {}
    p.write_text("[1]", encoding="utf-8")
    assert rt.read_json(p) == {}
    p.write_text("{nope", encoding="utf-8")
    assert rt.read_json(p) == {}
    p.write_text(json.dumps({"builder": {"gc": {"enabled": True}}, "x": 1}), encoding="utf-8")
    assert rt.json_has(p, {"builder": {"gc": {"enabled": True}}}) is True
    assert rt.json_has(p, {"x": 2}) is False


def test_license_notes() -> None:
    assert rt.license_note("colima") is None
    orb = rt.license_note("orbstack")
    assert orb is not None and "non-commercial" in orb and "$8/user/month" in orb
    dd = rt.license_note("docker-desktop")
    assert dd is not None and "250 employees" in dd and "US$10M" in dd
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_docker_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._docker_runtime'`.

- [ ] **Step 3: Implement** (`engine/src/devboost/modules/_docker_runtime.py`)

```python
"""Docker runtimes on macOS — the ``DockerRuntime`` protocol and what every runtime shares.

Three runtimes (spec §4): Colima (the default; MIT), OrbStack and Docker Desktop (both need
a paid plan for most work use — docs/docker-runtimes.md). Each lives in its own module
(``_docker_colima``, ``_docker_orbstack``, ``_docker_desktop``); ``runtime_for`` picks one.
Linux never reaches this file: it runs docker-ce (modules/docker.py).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from devboost.core.errors import InstallError
from devboost.core.userconfig import DockerRuntimeName
from devboost.model import Ctx

_GIB = 1024**3
#: Seconds to wait for a freshly started engine (a first Colima boot takes ~1 min).
ENGINE_TIMEOUT = 180.0

#: Test seams — a unit test never sleeps.
_sleep: Callable[[float], None] = time.sleep
_clock: Callable[[], float] = time.monotonic


class DockerRuntime(Protocol):
    """One way to run the Docker engine on a Mac. ``configure`` runs after ``install``
    and before ``start``; ``release_socket`` undoes what the runtime did to
    ``/var/run/docker.sock`` (a no-op for runtimes that manage it themselves)."""

    @property
    def name(self) -> DockerRuntimeName: ...
    @property
    def context_name(self) -> str: ...
    def daemon_config_path(self) -> Path: ...
    def installed(self, ctx: Ctx) -> bool: ...
    def install(self, ctx: Ctx) -> None: ...
    def configure(self, ctx: Ctx) -> None: ...
    def start(self, ctx: Ctx) -> None: ...
    def stop(self, ctx: Ctx) -> None: ...
    def disable_autostart(self, ctx: Ctx) -> None: ...
    def release_socket(self, ctx: Ctx) -> None: ...
    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool: ...
    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool: ...
    def restart_engine(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool: ...


@dataclass(frozen=True)
class VmSize:
    cpu: int
    memory_gib: int


def _sysctl_int(ctx: Ctx, key: str) -> int | None:
    res = ctx.ex.run(["sysctl", "-n", key])
    if not res.ok:
        return None
    try:
        return int(res.stdout.strip())
    except ValueError:
        return None


def vm_size(ctx: Ctx) -> VmSize:
    """Half the CPUs (at least 2) and a quarter of the RAM (at least 4 GiB) — spec §4."""
    ncpu = _sysctl_int(ctx, "hw.ncpu") or 4
    ram_gib = (_sysctl_int(ctx, "hw.memsize") or 16 * _GIB) // _GIB
    return VmSize(cpu=max(2, ncpu // 2), memory_gib=max(4, ram_gib // 4))


def rosetta_present(ctx: Ctx) -> bool:
    """Rosetta 2 can run x86_64 code (gates Colima's ``--vz-rosetta``, spec §0)."""
    return ctx.ex.run(["/usr/bin/arch", "-x86_64", "/usr/bin/true"]).ok


def current_context(ctx: Ctx) -> str:
    res = ctx.ex.run(["docker", "context", "show"])
    return res.stdout.strip() if res.ok else ""


def use_context(ctx: Ctx, name: str) -> None:
    res = ctx.ex.run(["docker", "context", "use", name])
    if not res.ok:
        raise InstallError("docker", f"docker context use {name}", res.code)


def engine_up(ctx: Ctx, context: str) -> bool:
    return ctx.ex.run(
        ["docker", "--context", context, "info", "--format", "{{.ServerVersion}}"]
    ).ok


def engine_verified(ctx: Ctx, context: str) -> bool:
    """The docker CLI points at ``context`` and the engine behind it answers (spec §4)."""
    return current_context(ctx) == context and engine_up(ctx, context)


def wait_for_engine(
    ctx: Ctx, context: str, *, timeout: float = ENGINE_TIMEOUT, interval: float = 3.0
) -> None:
    """Poll ``docker info`` until the engine answers, or raise after ``timeout`` s."""
    deadline = _clock() + timeout
    while not engine_up(ctx, context):
        if _clock() >= deadline:
            raise InstallError("docker", f"docker --context {context} info", 1)
        _sleep(interval)


def docker_config_path() -> Path:
    """The docker CLI's config.json (``$DOCKER_CONFIG`` or ``~/.docker``)."""
    base = os.environ.get("DOCKER_CONFIG")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".docker"
    return root / "config.json"


def read_json(path: Path) -> dict[str, Any]:
    """A JSON object from ``path``; ``{}`` when it is missing, invalid or not an object."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def json_has(path: Path, patch: Mapping[str, Any]) -> bool:
    data = read_json(path)
    return all(data.get(k) == v for k, v in patch.items())


_LICENSE_NOTES: dict[DockerRuntimeName, str] = {
    "orbstack": (
        "OrbStack's Free plan is for personal, non-commercial use only; work for an "
        "employer or clients needs OrbStack Pro ($8/user/month)."
    ),
    "docker-desktop": (
        "Docker Desktop is free only when the organisation the work is for has fewer than "
        "250 employees AND less than US$10M annual revenue; otherwise it needs a paid "
        "Docker subscription."
    ),
}


def license_note(name: DockerRuntimeName) -> str | None:
    """The commercial-use caveat for a non-default runtime (spec *Licensing*)."""
    return _LICENSE_NOTES.get(name)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_docker_runtime.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_docker_runtime.py tests/modules/test_docker_runtime.py
git commit -m "feat(docker): DockerRuntime protocol and shared macOS runtime helpers"
```

---

### Task 5: Colima runtime (+ PyYAML)

**Files:**
- Create: `engine/src/devboost/modules/_docker_colima.py`
- Modify: `engine/pyproject.toml`, `engine/uv.lock`
- Test: `engine/tests/modules/test_docker_colima.py` (create)

**Interfaces:**
- Consumes: Task 1 (`launchd.system_daemon`, `launchd.remove_daemon`, `launchd.label`), Task 2 (`pkg.brew_services`, `pkg.service_running`, `pkg.brew_link`), Task 4 helpers.
- Produces (module `devboost.modules._docker_colima`):
  - `FORMULAE = ("colima", "docker", "docker-compose", "docker-buildx")`, `CLI_PLUGINS_DIR = "/opt/homebrew/lib/docker/cli-plugins"`, `SOCKET_LABEL = "dev.devboost.docker-sock"`, `DOCKER_SOCK: Path` (test seam, default `/var/run/docker.sock`), `DISK_GIB = 100`.
  - `colima_home() -> Path` (mirrors Colima 0.10, D10); `ensure_colima_home() -> Path`.
  - `class Colima` implementing `DockerRuntime` (`name = "colima"`, `context_name = "colima"`), plus `socket_path() -> Path` and `start_args(ctx) -> list[str]`.

- [ ] **Step 1: Add PyYAML** (from `engine/`)

```bash
uv add 'pyyaml>=6.0.2'
uv add --dev 'types-PyYAML>=6.0'
```
Expected: `pyproject.toml` gains `"pyyaml>=6.0.2"` in `dependencies` and `"types-PyYAML>=6.0"` in `[dependency-groups] dev`; `uv.lock` is updated.

- [ ] **Step 2: Write the failing tests** (`tests/modules/test_docker_colima.py`)

```python
from __future__ import annotations

import json
import os
import plistlib
from pathlib import Path

import pytest
import yaml

from devboost.core.errors import ConfigError, InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import _docker_colima as col
from devboost.modules import _docker_runtime as rt
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3
RUNNING = (("info", "--json"), Result(0, stdout=json.dumps([{"name": "colima", "running": True}])))
STOPPED = (("info", "--json"), Result(0, stdout=json.dumps([{"name": "colima", "running": False}])))
SIZE = [
    (("hw.ncpu",), Result(0, stdout="10\n")),
    (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
]


@pytest.fixture(autouse=True)
def _seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    monkeypatch.setattr(col, "DOCKER_SOCK", tmp_path / "run" / "docker.sock")
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


# ── config dir (D10) ─────────────────────────────────────────────────────────
def test_home_uses_xdg_when_set(tmp_path: Path) -> None:
    assert col.colima_home() == tmp_path / ".config" / "colima"  # conftest sets XDG


def test_home_prefers_an_existing_dot_colima(tmp_path: Path) -> None:
    (tmp_path / ".colima").mkdir()
    assert col.colima_home() == tmp_path / ".colima"


def test_home_prefers_an_existing_colima_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ch").mkdir()
    monkeypatch.setenv("COLIMA_HOME", str(tmp_path / "ch"))
    assert col.colima_home() == tmp_path / "ch"


def test_home_without_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert col.colima_home() == tmp_path / ".colima"  # macOS fallback
    (tmp_path / ".config" / "colima").mkdir(parents=True)
    assert col.colima_home() == tmp_path / ".config" / "colima"  # launchd's view


def test_ensure_home_pins_the_xdg_dir(tmp_path: Path) -> None:
    assert col.ensure_colima_home() == tmp_path / ".config" / "colima"
    assert (tmp_path / ".config" / "colima").is_dir()


def test_ensure_home_keeps_an_existing_dot_colima(tmp_path: Path) -> None:
    (tmp_path / ".colima").mkdir()
    assert col.ensure_colima_home() == tmp_path / ".colima"
    assert not (tmp_path / ".config" / "colima").exists()


# ── install ──────────────────────────────────────────────────────────────────
def test_install_brews_only_missing_formulae_and_adds_the_plugin_dir(tmp_path: Path) -> None:
    ctx = _ctx(
        (("--versions", "colima"), Result(1)),
        (("--versions", "docker-buildx"), Result(1)),
        (("--cask", "docker-desktop"), Result(1)),
    )
    cfg = tmp_path / ".docker" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"cliPluginsExtraDirs": ["/x"], "auths": {}}), encoding="utf-8")
    col.Colima().install(ctx)
    assert ["brew", "install", "--formula", "-y", "colima", "docker-buildx"] in _calls(ctx)
    assert not any(c[:2] == ["brew", "link"] for c in _calls(ctx))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["cliPluginsExtraDirs"] == ["/x", col.CLI_PLUGINS_DIR]
    assert data["auths"] == {}


def test_install_takes_the_docker_names_back_from_docker_desktop() -> None:
    ctx = _ctx()  # everything "installed", including the docker-desktop cask
    col.Colima().install(ctx)
    assert ["brew", "link", "--overwrite", "docker", "docker-compose"] in _calls(ctx)
    assert not any(c[:2] == ["brew", "install"] for c in _calls(ctx))


def test_installed_needs_every_formula() -> None:
    assert col.Colima().installed(_ctx()) is True
    assert col.Colima().installed(_ctx((("--versions", "docker-compose"), Result(1)))) is False


# ── configure ────────────────────────────────────────────────────────────────
def test_start_args_with_and_without_rosetta() -> None:
    assert col.Colima().start_args(_ctx(*SIZE)) == [
        "--vm-type", "vz", "--vz-rosetta", "--mount-type", "virtiofs",
        "--cpu", "5", "--memory", "6", "--disk", "100",
    ]
    no_rosetta = _ctx(*SIZE, (("-x86_64",), Result(1)))
    assert "--vz-rosetta" not in col.Colima().start_args(no_rosetta)


def test_first_configure_creates_the_vm_then_hands_it_to_brew_services(tmp_path: Path) -> None:
    ctx = _ctx(*SIZE, (("launchctl", "print"), Result(1)))
    col.Colima().configure(ctx)
    calls = _calls(ctx)
    start = calls.index(["colima", "start", *col.Colima().start_args(_ctx(*SIZE))])
    assert calls[start + 1] == ["colima", "stop"]
    home = tmp_path / ".config" / "colima"
    plist = tmp_path / "LaunchDaemons" / f"{col.SOCKET_LABEL}.plist"
    assert ["sudo", "tee", str(plist)] in calls
    assert ["sudo", "launchctl", "bootstrap", "system", str(plist)] in calls
    tee = calls.index(["sudo", "tee", str(plist)])
    body = ctx.ex.stdins[tee]  # type: ignore[attr-defined]
    assert plistlib.loads(body.encode("utf-8"))["ProgramArguments"] == [
        "/bin/ln", "-sf", str(home / "default" / "docker.sock"), str(col.DOCKER_SOCK)
    ]


def test_configure_does_not_recreate_an_existing_vm(tmp_path: Path) -> None:
    yaml_path = tmp_path / ".config" / "colima" / "default" / "colima.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("cpu: 3\n", encoding="utf-8")
    ctx = _ctx()
    col.Colima().configure(ctx)
    assert not any(c[:2] == ["colima", "start"] for c in _calls(ctx))


def test_configure_raises_when_the_vm_cannot_be_created() -> None:
    with pytest.raises(InstallError, match="colima start"):
        col.Colima().configure(_ctx(*SIZE, (("colima", "start"), Result(1))))


# ── start / stop ─────────────────────────────────────────────────────────────
def test_start_registers_the_service_when_not_running() -> None:
    ctx = _ctx(STOPPED)
    col.Colima().start(ctx)
    assert ["brew", "services", "start", "colima"] in _calls(ctx)
    assert ["docker", "--context", "colima", "info", "--format", "{{.ServerVersion}}"] in _calls(
        ctx
    )


def test_start_leaves_a_running_service_alone() -> None:
    ctx = _ctx(RUNNING)
    col.Colima().start(ctx)
    assert ["brew", "services", "start", "colima"] not in _calls(ctx)


def test_start_raises_when_brew_services_fails() -> None:
    with pytest.raises(InstallError, match="brew services start colima"):
        col.Colima().start(_ctx(STOPPED, (("services", "start"), Result(1))))


def test_stop_and_disable_autostart() -> None:
    ctx = _ctx()
    col.Colima().stop(ctx)
    col.Colima().disable_autostart(ctx)
    assert _calls(ctx) == [
        ["brew", "services", "stop", "colima"],
        ["colima", "stop"],
        ["brew", "services", "stop", "colima"],
    ]


# ── socket ───────────────────────────────────────────────────────────────────
def test_release_socket_removes_the_daemon_and_our_link(tmp_path: Path) -> None:
    col.DOCKER_SOCK.parent.mkdir(parents=True)
    os.symlink(col.Colima().socket_path(), col.DOCKER_SOCK)
    ctx = _ctx()
    col.Colima().release_socket(ctx)
    assert ["sudo", "launchctl", "bootout", f"system/{col.SOCKET_LABEL}"] in _calls(ctx)
    assert ["sudo", "rm", "-f", str(col.DOCKER_SOCK)] in _calls(ctx)


def test_release_socket_keeps_someone_elses_link(tmp_path: Path) -> None:
    col.DOCKER_SOCK.parent.mkdir(parents=True)
    os.symlink(tmp_path / "orbstack.sock", col.DOCKER_SOCK)
    ctx = _ctx()
    col.Colima().release_socket(ctx)
    assert ["sudo", "rm", "-f", str(col.DOCKER_SOCK)] not in _calls(ctx)


# ── daemon config (colima.yaml `docker:`) ─────────────────────────────────────
GC = {"builder": {"gc": {"enabled": True, "defaultKeepStorage": "20GB"}}}


def _yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / ".config" / "colima" / "default" / "colima.yaml"
    p.parent.mkdir(parents=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_merge_daemon_config_keeps_other_keys(tmp_path: Path) -> None:
    p = _yaml(tmp_path, "cpu: 5\ndocker:\n  log-driver: json-file\n")
    assert col.Colima().merge_daemon_config(_ctx(), GC) is True
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["cpu"] == 5
    assert data["docker"] == {"log-driver": "json-file", **GC}
    assert col.Colima().daemon_config_has(GC) is True
    assert col.Colima().merge_daemon_config(_ctx(), GC) is False  # idempotent


def test_daemon_config_has_is_false_without_the_key(tmp_path: Path) -> None:
    _yaml(tmp_path, "docker: {}\n")
    assert col.Colima().daemon_config_has(GC) is False


def test_invalid_yaml_is_a_config_error(tmp_path: Path) -> None:
    _yaml(tmp_path, "docker: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        col.Colima().daemon_config_has(GC)


def test_restart_engine_only_when_the_service_runs() -> None:
    ctx = _ctx(RUNNING)
    col.Colima().restart_engine(ctx)
    assert ["brew", "services", "restart", "colima"] in _calls(ctx)
    idle = _ctx(STOPPED)
    col.Colima().restart_engine(idle)
    assert ["brew", "services", "restart", "colima"] not in _calls(idle)


def test_verify() -> None:
    show = (("context", "show"), Result(0, stdout="colima\n"))
    assert col.Colima().verify(_ctx(show)) is True
    assert col.Colima().verify(_ctx(show, (("--versions", "colima"), Result(1)))) is False
    assert col.Colima().verify(_ctx((("context", "show"), Result(0, stdout="default")))) is False
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_docker_colima.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._docker_colima'`.

- [ ] **Step 4: Implement** (`engine/src/devboost/modules/_docker_colima.py`)

```python
"""Colima — the default Docker runtime on macOS (MIT; spec §4, plan D10–D13).

Colima runs dockerd in a Lima VM (Apple Virtualization.framework, virtiofs mounts). The
brew formulae give the docker CLI, compose and buildx; ``brew services`` keeps Colima
running across logins; a root LaunchDaemon re-creates ``/var/run/docker.sock`` at boot.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, launchd, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import (
    docker_config_path,
    engine_verified,
    read_json,
    rosetta_present,
    vm_size,
    wait_for_engine,
)

FORMULAE: tuple[str, ...] = ("colima", "docker", "docker-compose", "docker-buildx")
#: Where the brew compose/buildx formulae put their CLI plugins.
CLI_PLUGINS_DIR = "/opt/homebrew/lib/docker/cli-plugins"
SOCKET_LABEL = launchd.label("docker-sock")
#: The well-known socket third-party tools (Testcontainers, IDEs) expect. Module attribute
#: so tests can redirect it.
DOCKER_SOCK = Path("/var/run/docker.sock")
DISK_GIB = 100


def colima_home() -> Path:
    """Colima's config dir, resolved the way Colima 0.10 resolves it (config/files.go)."""
    explicit = os.environ.get("COLIMA_HOME")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    home = Path(os.environ["HOME"])
    dot = home / ".colima"
    if dot.exists():
        return dot
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    xdg_dir = (Path(xdg) if xdg else home / ".config") / "colima"
    if xdg or xdg_dir.exists():
        return xdg_dir
    return dot


def ensure_colima_home() -> Path:
    """Create the XDG config dir before Colima's first run, unless one already exists.

    Shells export XDG_CONFIG_HOME (env.sh) but ``brew services`` starts Colima from launchd
    without it; with ``~/.config/colima`` present both resolve to it (plan D10).
    """
    home = Path(os.environ["HOME"])
    explicit = os.environ.get("COLIMA_HOME")
    if (explicit and Path(explicit).exists()) or (home / ".colima").exists():
        return colima_home()
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    ((Path(xdg) if xdg else home / ".config") / "colima").mkdir(parents=True, exist_ok=True)
    return colima_home()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML ({exc})") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


class Colima:
    name: DockerRuntimeName = "colima"
    context_name = "colima"

    def daemon_config_path(self) -> Path:
        return colima_home() / "default" / "colima.yaml"

    def socket_path(self) -> Path:
        return colima_home() / "default" / "docker.sock"

    def installed(self, ctx: Ctx) -> bool:
        return all(pkg.installed(ctx, f) for f in FORMULAE)

    def install(self, ctx: Ctx) -> None:
        missing = [f for f in FORMULAE if not pkg.installed(ctx, f)]
        if missing:
            pkg.install(ctx, *missing)
        if pkg.cask_installed(ctx, "docker-desktop"):
            # Docker Desktop's cask links its own docker/docker-compose into the brew
            # prefix (plan D14); take the names back for the formulae.
            pkg.brew_link(ctx, "docker", "docker-compose", overwrite=True)
        self._cli_plugins(ctx)

    def _cli_plugins(self, ctx: Ctx) -> None:
        path = docker_config_path()
        dirs = read_json(path).get("cliPluginsExtraDirs")
        current = [d for d in dirs if isinstance(d, str)] if isinstance(dirs, list) else []
        if CLI_PLUGINS_DIR not in current:
            config.json_merge(
                ctx, str(path), {"cliPluginsExtraDirs": [*current, CLI_PLUGINS_DIR]}
            )

    def start_args(self, ctx: Ctx) -> list[str]:
        size = vm_size(ctx)
        args = ["--vm-type", "vz"]
        if rosetta_present(ctx):
            args.append("--vz-rosetta")
        else:
            log.info("colima: Rosetta 2 is absent — amd64 images will run under qemu (slower)")
        return [
            *args,
            "--mount-type", "virtiofs",
            "--cpu", str(size.cpu),
            "--memory", str(size.memory_gib),
            "--disk", str(DISK_GIB),
        ]

    def configure(self, ctx: Ctx) -> None:
        ensure_colima_home()
        if not self.daemon_config_path().exists():
            # First run: create the VM, which saves these flags to colima.yaml, then stop
            # it so `brew services` (a bare `colima start -f`) owns it from now on (D11).
            argv = ["colima", "start", *self.start_args(ctx)]
            res = ctx.ex.run(argv)
            if not res.ok:
                raise InstallError("colima", " ".join(argv), res.code)
            ctx.ex.run(["colima", "stop"])
        # macOS empties /var/run at boot, so the link is re-made by a root daemon (D13).
        launchd.system_daemon(
            ctx,
            SOCKET_LABEL,
            ["/bin/ln", "-sf", str(self.socket_path()), str(DOCKER_SOCK)],
            run_at_load=True,
        )

    def start(self, ctx: Ctx) -> None:
        if not pkg.service_running(ctx, "colima"):
            res = pkg.brew_services(ctx, "start", "colima")
            if not res.ok:
                raise InstallError("colima", "brew services start colima", res.code)
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        pkg.brew_services(ctx, "stop", "colima")
        ctx.ex.run(["colima", "stop"])  # a VM started by hand, outside brew services

    def disable_autostart(self, ctx: Ctx) -> None:
        pkg.brew_services(ctx, "stop", "colima")  # also unregisters the login agent

    def release_socket(self, ctx: Ctx) -> None:
        launchd.remove_daemon(ctx, SOCKET_LABEL)
        if DOCKER_SOCK.is_symlink() and Path(os.readlink(DOCKER_SOCK)) == self.socket_path():
            ctx.ex.run(["rm", "-f", str(DOCKER_SOCK)], sudo=True)

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        path = self.daemon_config_path()
        data = _load_yaml(path)
        current = data.get("docker")
        docker: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        merged = {**docker, **patch}
        if merged == docker:
            return False
        data["docker"] = merged
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return True

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        docker = _load_yaml(self.daemon_config_path()).get("docker")
        return isinstance(docker, dict) and all(docker.get(k) == v for k, v in patch.items())

    def restart_engine(self, ctx: Ctx) -> None:
        if not pkg.service_running(ctx, "colima"):
            return  # the new config is read at the next start
        res = pkg.brew_services(ctx, "restart", "colima")
        if not res.ok:
            raise InstallError("colima", "brew services restart colima", res.code)
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_docker_colima.py tests/modules/test_docker_runtime.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. If mypy reports that `Colima` does not satisfy `DockerRuntime`, it is because of the `name` attribute. Keep the explicit `name: DockerRuntimeName = "colima"` annotation: a plain `name = "colima"` infers `str`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/devboost/modules/_docker_colima.py \
  tests/modules/test_docker_colima.py
git commit -m "feat(docker): Colima runtime for macOS (brew services, socket daemon, colima.yaml)"
```

---

### Task 6: OrbStack and Docker Desktop runtimes

**Files:**
- Create: `engine/src/devboost/modules/_docker_orbstack.py`, `engine/src/devboost/modules/_docker_desktop.py`
- Test: `engine/tests/modules/test_docker_orbstack_desktop.py` (create)

**Interfaces:**
- Consumes: Task 2 (`pkg.brew_unlink`), Task 4 helpers, M1 `pkg.install_cask`/`cask_installed`, `config.json_merge`, `NeedsUser`.
- Produces:
  - `devboost.modules._docker_orbstack.OrbStack` (`name = "orbstack"`, `context_name = "orbstack"`, daemon config `~/.orbstack/config/docker.json`).
  - `devboost.modules._docker_desktop.DockerDesktop` (`name = "docker-desktop"`, `context_name = "desktop-linux"`, daemon config `~/.docker/daemon.json`); `settings_path() -> Path`; `update_settings(path, values: Mapping[str, object]) -> bool`.

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_docker_orbstack_desktop.py`)

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _docker_runtime as rt
from devboost.modules._docker_desktop import DockerDesktop, settings_path, update_settings
from devboost.modules._docker_orbstack import OrbStack
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3
SIZE = [
    (("hw.ncpu",), Result(0, stdout="10\n")),
    (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
]
GC = {"builder": {"gc": {"enabled": True, "defaultKeepStorage": "20GB"}}}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


# ── OrbStack ─────────────────────────────────────────────────────────────────
def test_orbstack_install_is_the_cask() -> None:
    ctx = _ctx()
    OrbStack().install(ctx)
    assert _calls(ctx) == [["brew", "install", "--cask", "-y", "--adopt", "orbstack"]]


def test_orbstack_configure_sets_size_and_login_start() -> None:
    ctx = _ctx(*SIZE)
    OrbStack().configure(ctx)
    sets = [c for c in _calls(ctx) if c[:3] == ["orb", "config", "set"]]
    assert sets == [
        ["orb", "config", "set", "cpu", "5"],
        ["orb", "config", "set", "memory_mib", "6144"],
        ["orb", "config", "set", "app.start_at_login", "true"],
    ]


def test_orbstack_before_first_launch_needs_the_user() -> None:
    with pytest.raises(NeedsUser, match="open -a OrbStack"):
        OrbStack().configure(_ctx(*SIZE, (("orb", "config"), Result(1))))
    with pytest.raises(NeedsUser):
        OrbStack().start(_ctx((("orb", "start"), Result(1))))


def test_orbstack_start_stop_autostart() -> None:
    ctx = _ctx()
    OrbStack().start(ctx)
    OrbStack().stop(ctx)
    OrbStack().disable_autostart(ctx)
    OrbStack().release_socket(ctx)
    assert _calls(ctx) == [
        ["orb", "start"],
        ["docker", "--context", "orbstack", "info", "--format", "{{.ServerVersion}}"],
        ["orb", "stop"],
        ["orb", "config", "set", "app.start_at_login", "false"],
    ]


def test_orbstack_daemon_config(tmp_path: Path) -> None:
    ctx = _ctx()
    orb = OrbStack()
    assert orb.daemon_config_path() == tmp_path / ".orbstack" / "config" / "docker.json"
    assert orb.merge_daemon_config(ctx, GC) is True
    assert orb.daemon_config_has(GC) is True
    assert orb.merge_daemon_config(ctx, GC) is False
    orb.restart_engine(ctx)
    assert ["orb", "restart", "docker"] in _calls(ctx)


def test_orbstack_verify() -> None:
    show = (("context", "show"), Result(0, stdout="orbstack\n"))
    assert OrbStack().verify(_ctx(show)) is True
    assert OrbStack().verify(_ctx(show, (("--cask", "orbstack"), Result(1)))) is False


# ── Docker Desktop ───────────────────────────────────────────────────────────
def test_settings_path(tmp_path: Path) -> None:
    assert settings_path() == (
        tmp_path / "Library" / "Group Containers" / "group.com.docker" / "settings-store.json"
    )


def test_update_settings_keeps_the_files_own_key_spelling(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"cpus": 2, "AutoStart": False, "Other": 1}), encoding="utf-8")
    assert update_settings(p, {"Cpus": 5, "MemoryMiB": 6144, "AutoStart": True}) is True
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "cpus": 5, "AutoStart": True, "Other": 1, "MemoryMiB": 6144,
    }
    assert update_settings(p, {"Cpus": 5}) is False


def test_desktop_install_frees_the_docker_names_first() -> None:
    ctx = _ctx()  # the docker formula is installed
    DockerDesktop().install(ctx)
    assert _calls(ctx)[-2:] == [
        ["brew", "unlink", "docker", "docker-compose"],
        ["brew", "install", "--cask", "-y", "--adopt", "docker-desktop"],
    ]


def test_desktop_install_without_the_formula() -> None:
    ctx = _ctx((("--versions", "docker"), Result(1)))
    DockerDesktop().install(ctx)
    assert ["brew", "unlink", "docker", "docker-compose"] not in _calls(ctx)


def test_desktop_configure_before_first_launch_needs_the_user() -> None:
    with pytest.raises(NeedsUser, match="open -a Docker"):
        DockerDesktop().configure(_ctx(*SIZE))


def test_desktop_configure_writes_settings_and_restarts_a_running_app() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"AutoStart": False}), encoding="utf-8")
    ctx = _ctx(*SIZE)  # engine answers → running
    DockerDesktop().configure(ctx)
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "AutoStart": True, "Cpus": 5, "MemoryMiB": 6144,
    }
    assert ["docker", "desktop", "restart"] in _calls(ctx)


def test_desktop_configure_leaves_a_stopped_app_alone() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    ctx = _ctx(*SIZE, (("info",), Result(1)))
    DockerDesktop().configure(ctx)
    assert ["docker", "desktop", "restart"] not in _calls(ctx)


def test_desktop_start_stop_autostart() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"AutoStart": True}), encoding="utf-8")
    ctx = _ctx()
    DockerDesktop().start(ctx)
    DockerDesktop().stop(ctx)
    DockerDesktop().disable_autostart(ctx)
    assert ["docker", "desktop", "start"] in _calls(ctx)
    assert ["docker", "desktop", "stop"] in _calls(ctx)
    assert json.loads(p.read_text(encoding="utf-8")) == {"AutoStart": False}
    with pytest.raises(NeedsUser):
        DockerDesktop().start(_ctx((("desktop", "start"), Result(1))))


def test_desktop_daemon_config(tmp_path: Path) -> None:
    ctx = _ctx()
    dd = DockerDesktop()
    assert dd.daemon_config_path() == tmp_path / ".docker" / "daemon.json"
    assert dd.merge_daemon_config(ctx, GC) is True
    assert dd.daemon_config_has(GC) is True
    dd.restart_engine(ctx)
    assert ["docker", "desktop", "restart"] in _calls(ctx)


def test_desktop_verify_uses_desktop_linux_context() -> None:
    show = (("context", "show"), Result(0, stdout="desktop-linux\n"))
    assert DockerDesktop().verify(_ctx(show)) is True
    assert DockerDesktop().verify(_ctx()) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_docker_orbstack_desktop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._docker_desktop'`.

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/_docker_orbstack.py`:

```python
"""OrbStack — opt-in Docker runtime on macOS (paid for commercial use; plan D3, D15)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import engine_verified, json_has, vm_size, wait_for_engine

CASK = "orbstack"


def _first_launch() -> NeedsUser:
    return NeedsUser(
        "OrbStack has not finished its first launch",
        "open -a OrbStack and finish setup (the Free plan is non-commercial — choose Pro "
        "for work), then run: devboost docker use orbstack",
    )


class OrbStack:
    name: DockerRuntimeName = "orbstack"
    context_name = "orbstack"

    def daemon_config_path(self) -> Path:
        return Path(os.environ["HOME"]) / ".orbstack" / "config" / "docker.json"

    def installed(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, CASK)

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, CASK)

    def _set(self, ctx: Ctx, key: str, value: str) -> None:
        if not ctx.ex.run(["orb", "config", "set", key, value]).ok:
            raise _first_launch()

    def configure(self, ctx: Ctx) -> None:
        size = vm_size(ctx)
        self._set(ctx, "cpu", str(size.cpu))
        self._set(ctx, "memory_mib", str(size.memory_gib * 1024))
        self._set(ctx, "app.start_at_login", "true")

    def start(self, ctx: Ctx) -> None:
        if not ctx.ex.run(["orb", "start"]).ok:
            raise _first_launch()
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        ctx.ex.run(["orb", "stop"])

    def disable_autostart(self, ctx: Ctx) -> None:
        ctx.ex.run(["orb", "config", "set", "app.start_at_login", "false"])

    def release_socket(self, ctx: Ctx) -> None:
        return None  # OrbStack manages /var/run/docker.sock itself

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        return config.json_merge(ctx, str(self.daemon_config_path()), patch)

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return json_has(self.daemon_config_path(), patch)

    def restart_engine(self, ctx: Ctx) -> None:
        res = ctx.ex.run(["orb", "restart", "docker"])
        if not res.ok:
            raise InstallError("orbstack", "orb restart docker", res.code)
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
```

`engine/src/devboost/modules/_docker_desktop.py`:

```python
"""Docker Desktop — opt-in Docker runtime on macOS (paid above 250 staff / $10M; D3, D14)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import (
    engine_up,
    engine_verified,
    json_has,
    read_json,
    vm_size,
    wait_for_engine,
)

CASK = "docker-desktop"


def settings_path() -> Path:
    """Docker Desktop's settings file (4.35+). Created by the app's first launch."""
    return (
        Path(os.environ["HOME"]) / "Library" / "Group Containers" / "group.com.docker"
        / "settings-store.json"
    )


def update_settings(path: Path, values: Mapping[str, object]) -> bool:
    """Set settings keys, keeping the spelling the file already uses (plan D14).

    Docker does not document these keys (docker/docs#23706), so an existing key is matched
    case-insensitively and the given name is used only when the file has none.
    """
    data = read_json(path)
    changed = False
    for preferred, value in values.items():
        key = next((k for k in data if k.lower() == preferred.lower()), preferred)
        if data.get(key) != value:
            data[key] = value
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def _first_launch() -> NeedsUser:
    return NeedsUser(
        "Docker Desktop has not finished its first launch",
        "open -a Docker, accept the Docker Subscription Service Agreement (free only under "
        "250 employees and US$10M revenue), then run: devboost docker use docker-desktop",
    )


class DockerDesktop:
    name: DockerRuntimeName = "docker-desktop"
    context_name = "desktop-linux"

    def daemon_config_path(self) -> Path:
        return Path(os.environ["HOME"]) / ".docker" / "daemon.json"

    def installed(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, CASK)

    def install(self, ctx: Ctx) -> None:
        if pkg.installed(ctx, "docker"):
            # The cask links its own docker + docker-compose into the brew prefix, and brew
            # will not overwrite the Colima formulae's links (plan D14).
            pkg.brew_unlink(ctx, "docker", "docker-compose")
        pkg.install_cask(ctx, CASK)

    def _desktop(self, ctx: Ctx, verb: str) -> None:
        res = ctx.ex.run(["docker", "desktop", verb])
        if not res.ok:
            raise InstallError("docker-desktop", f"docker desktop {verb}", res.code)

    def configure(self, ctx: Ctx) -> None:
        path = settings_path()
        if not path.exists():
            raise _first_launch()
        size = vm_size(ctx)
        changed = update_settings(
            path, {"Cpus": size.cpu, "MemoryMiB": size.memory_gib * 1024, "AutoStart": True}
        )
        if changed and engine_up(ctx, self.context_name):
            self._desktop(ctx, "restart")

    def start(self, ctx: Ctx) -> None:
        if not ctx.ex.run(["docker", "desktop", "start"]).ok:
            raise _first_launch()
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        ctx.ex.run(["docker", "desktop", "stop"])

    def disable_autostart(self, ctx: Ctx) -> None:
        path = settings_path()
        if path.exists():
            update_settings(path, {"AutoStart": False})

    def release_socket(self, ctx: Ctx) -> None:
        return None  # Docker Desktop manages /var/run/docker.sock itself

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        return config.json_merge(ctx, str(self.daemon_config_path()), patch)

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return json_has(self.daemon_config_path(), patch)

    def restart_engine(self, ctx: Ctx) -> None:
        self._desktop(ctx, "restart")
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_docker_orbstack_desktop.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_docker_orbstack.py src/devboost/modules/_docker_desktop.py \
  tests/modules/test_docker_orbstack_desktop.py
git commit -m "feat(docker): opt-in OrbStack and Docker Desktop runtimes for macOS"
```

---

### Task 7: `docker` and `docker-build-gc` on macOS

**Files:**
- Modify: `engine/src/devboost/modules/_docker_runtime.py` (append `runtime_for`, `selected_runtime`), `engine/src/devboost/modules/docker.py`, `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/modules/test_docker_macos.py` (create)

**Interfaces:**
- Consumes: Tasks 3–6; M2 `Module.os_strategy`; M3 `Homebrew`, `Rosetta` (A1/A2, the import path recorded in Task 0).
- Produces:
  - `_docker_runtime.runtime_for(name: DockerRuntimeName) -> DockerRuntime`, `_docker_runtime.selected_runtime() -> DockerRuntime`.
  - `docker.BUILDER_GC` (renamed from `_BUILDER_GC`, now public; Task 12 imports it).
  - `Docker.per_os.macos` and `DockerBuildCacheGc.per_os.macos`. Both are driven by `selected_runtime()`.

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_docker_macos.py`)

```python
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from devboost.core import log
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.userconfig import DockerRuntimeName, set_user_value
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import _docker_runtime as rt
from devboost.modules import docker as docker_mod
from devboost.modules._docker_colima import Colima
from devboost.modules._docker_desktop import DockerDesktop
from devboost.modules._docker_orbstack import OrbStack
from devboost.modules.docker import BUILDER_GC, Docker, DockerBuildCacheGc

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _RecRuntime:
    """A DockerRuntime that records each call as a `rt <name> <method>` command."""

    def __init__(self, name: DockerRuntimeName, *, merged: bool = True) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._merged = merged

    def _rec(self, ctx: Ctx, what: str) -> None:
        ctx.ex.run(["rt", self.name, what])

    def daemon_config_path(self) -> Path:
        return Path("/nonexistent")

    def installed(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:
        self._rec(ctx, "install")

    def configure(self, ctx: Ctx) -> None:
        self._rec(ctx, "configure")

    def start(self, ctx: Ctx) -> None:
        self._rec(ctx, "start")

    def stop(self, ctx: Ctx) -> None:
        self._rec(ctx, "stop")

    def disable_autostart(self, ctx: Ctx) -> None:
        self._rec(ctx, "disable_autostart")

    def release_socket(self, ctx: Ctx) -> None:
        self._rec(ctx, "release_socket")

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        self._rec(ctx, "merge_daemon_config")
        return self._merged

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return patch == BUILDER_GC

    def restart_engine(self, ctx: Ctx) -> None:
        self._rec(ctx, "restart_engine")

    def verify(self, ctx: Ctx) -> bool:
        return True


def _use(monkeypatch: pytest.MonkeyPatch, runtime: _RecRuntime) -> None:
    monkeypatch.setattr(docker_mod, "selected_runtime", lambda: runtime)


def test_runtime_for_every_name() -> None:
    assert isinstance(rt.runtime_for("colima"), Colima)
    assert isinstance(rt.runtime_for("orbstack"), OrbStack)
    assert isinstance(rt.runtime_for("docker-desktop"), DockerDesktop)


def test_selected_runtime_follows_the_config() -> None:
    assert isinstance(rt.selected_runtime(), Colima)
    set_user_value("docker_runtime", "orbstack")
    assert isinstance(rt.selected_runtime(), OrbStack)


def test_docker_on_macos_brings_up_the_selected_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    Docker().install(ctx)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["rt", "colima", "install"],
        ["rt", "colima", "configure"],
        ["rt", "colima", "start"],
        ["docker", "context", "use", "ctx-colima"],
    ]
    assert Docker().verify(ctx) is True


def test_docker_warns_about_a_paid_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("orbstack"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    Docker().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert any("non-commercial" in w for w in warned)


def test_docker_on_macos_never_touches_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    Docker().install(ctx)
    assert not any("systemctl" in c or "usermod" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_build_gc_on_macos_merges_and_restarts_only_on_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _RecRuntime("colima", merged=True))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    DockerBuildCacheGc().install(ctx)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["rt", "colima", "merge_daemon_config"],
        ["rt", "colima", "restart_engine"],
    ]
    assert DockerBuildCacheGc().verify(ctx) is True
    _use(monkeypatch, _RecRuntime("colima", merged=False))
    idle = Ctx(os=MAC, ex=FakeExecutor())
    DockerBuildCacheGc().install(idle)
    assert idle.ex.calls == [["rt", "colima", "merge_daemon_config"]]  # type: ignore[attr-defined]


def test_linux_docker_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "selected_runtime", lambda: pytest.fail("macOS only"))
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(present={"dockerd"}))
    Docker().install(ctx)
    assert ["sudo", "systemctl", "enable", "--now", "docker.service"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_both_plan_on_macos_and_fedora(tmp_path: Path) -> None:
    modules = load()
    for os_info in (MAC, FEDORA):
        plan = build_plan(["docker", "docker-build-gc"], modules, os_info,
                          gpu_marker=tmp_path / "none")
        assert {p.name: p.skip_reason for p in plan} == {
            "docker": None, "docker-build-gc": None,
        }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_docker_macos.py -v`
Expected: FAIL with `ImportError: cannot import name 'BUILDER_GC'`.

- [ ] **Step 3: Implement**

Append to `engine/src/devboost/modules/_docker_runtime.py`:

```python
def runtime_for(name: DockerRuntimeName) -> DockerRuntime:
    """The runtime implementation for ``name``."""
    # Imported here: each runtime module imports this module's helpers.
    from devboost.modules._docker_colima import Colima
    from devboost.modules._docker_desktop import DockerDesktop
    from devboost.modules._docker_orbstack import OrbStack

    runtimes: dict[DockerRuntimeName, DockerRuntime] = {
        "colima": Colima(),
        "orbstack": OrbStack(),
        "docker-desktop": DockerDesktop(),
    }
    return runtimes[name]


def selected_runtime() -> DockerRuntime:
    """The runtime chosen by env > config.toml > colima (spec §4)."""
    return runtime_for(selected_docker_runtime())
```

and extend its import: `from devboost.core.userconfig import DockerRuntimeName, selected_docker_runtime`.

In `engine/src/devboost/modules/docker.py`:

1. Imports: add `from dataclasses import dataclass`, `from devboost.core import log`, change the model import to `from devboost.model import AptRepo, Ctx, Module` (unchanged) and add

```python
from devboost.modules._docker_runtime import license_note, selected_runtime, use_context
from devboost.modules.macos_base import Homebrew, Rosetta  # path per Task 0 (A1/A2)
```

2. Rename `_BUILDER_GC` to `BUILDER_GC` (the definition and its one use in `DockerBuildCacheGc.install`).

3. Above `class Docker`, add:

```python
@dataclass(frozen=True)
class _MacDocker:
    """macOS: bring up the selected runtime — Colima unless configured otherwise (§4)."""

    def verify(self, ctx: Ctx) -> bool:
        return selected_runtime().verify(ctx)

    def install(self, ctx: Ctx) -> None:
        rt = selected_runtime()
        note = license_note(rt.name)
        if note:
            log.warn(f"docker: {rt.name} — {note}")
        rt.install(ctx)
        rt.configure(ctx)
        rt.start(ctx)
        use_context(ctx, rt.context_name)
```

4. In `class Docker`, add the class attributes and the strategy hand-off:

```python
    requires = (Homebrew,)  # families=("macos",): dropped from Linux plans (spec §1)
    after = (Rosetta,)  # --vz-rosetta needs Rosetta when both are in the plan (§0)
    per_os = OsMap(macos=_MacDocker())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        ...  # the existing Linux body, unchanged

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        ...  # the existing Linux body, unchanged
```

(The `...` lines stand for the method bodies already in the file. Keep them byte-for-byte after the new first statement.)

5. Above `class DockerBuildCacheGc`, add:

```python
@dataclass(frozen=True)
class _MacBuildGc:
    """macOS: the same cache cap, in the selected runtime's daemon config (plan D2)."""

    def verify(self, ctx: Ctx) -> bool:
        return selected_runtime().daemon_config_has(BUILDER_GC)

    def install(self, ctx: Ctx) -> None:
        rt = selected_runtime()
        if rt.merge_daemon_config(ctx, BUILDER_GC):
            rt.restart_engine(ctx)
```

and give `DockerBuildCacheGc` `per_os = OsMap(macos=_MacBuildGc())` with the same `os_strategy` first statement in `verify` and `install`.

6. `tests/core/test_macos_contract.py`: delete `"docker"` and `"docker-build-gc"` from `KNOWN_GAPS`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_docker_macos.py tests/modules/test_docker_ddev.py tests/core/test_macos_contract.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. The existing Linux tests in `test_docker_ddev.py` pass unchanged. If one of them references `_BUILDER_GC`, rename it there too.

- [ ] **Step 5: Run the whole suite** (the new `requires`/`after` edges touch every plan that contains `docker`)

Run: `uv run pytest`
Expected: PASS. If a profile fixture test fails with an unknown module `homebrew`/`rosetta`, the M3 classes are not registered under those names. Fix the import path recorded in Task 0.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/_docker_runtime.py src/devboost/modules/docker.py \
  tests/modules/test_docker_macos.py tests/core/test_macos_contract.py
git commit -m "feat(docker): docker and docker-build-gc run the selected runtime on macOS"
```

---

### Task 8: ddev, ddev-remote, data-services and Aspire on macOS

**Files:**
- Modify: `engine/src/devboost/modules/ddev.py`, `engine/src/devboost/modules/dev_stacks.py`, `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/modules/test_ddev_aspire_macos.py` (create)

**Interfaces:**
- Consumes: M1 `pkg.install`/`pkg.installed` (brew on macOS), `NeedsUser`; M2 `os_strategy`.
- Produces: `Ddev.per_os.macos` (`_MacDdev`, with `DDEV_FORMULA = "ddev/ddev/ddev"`); `DdevRemote.portable = True`; `DataServices.portable = True`; `Aspire.per_os.macos` (`_MacAspire`).

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_ddev_aspire_macos.py`)

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.ddev import Ddev, DdevRemote
from devboost.modules.dev_stacks import Aspire, DataServices
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
MAC_SSH = OsInfo("macos", "macos", "aarch64", headless=True)


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


def test_ddev_brews_the_tap_formula_and_mkcert() -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions",), Result(1))]))
    Ddev().install(ctx)
    calls = _calls(ctx)
    assert ["brew", "install", "--formula", "-y", "ddev/ddev/ddev", "mkcert"] in calls
    assert calls[-1] == ["mkcert", "-install"]
    assert not any(c[0] in ("dnf", "apt-get", "sudo") for c in calls)


def test_ddev_skips_what_is_already_brewed() -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    Ddev().install(ctx)
    assert _calls(ctx)[-1] == ["mkcert", "-install"]
    assert not any(c[:2] == ["brew", "install"] for c in _calls(ctx))


def test_ddev_untrusted_ca_needs_the_user() -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("mkcert", "-install"), Result(1))]))
    with pytest.raises(NeedsUser, match="mkcert -install"):
        Ddev().install(ctx)


def test_ddev_verify_reads_brew_not_path() -> None:
    assert Ddev().verify(Ctx(os=MAC, ex=RuleExecutor())) is True
    missing = RuleExecutor(rules=[(("--versions", "mkcert"), Result(1))])
    assert Ddev().verify(Ctx(os=MAC, ex=missing)) is False


def test_ddev_remote_and_data_services_are_portable() -> None:
    assert DdevRemote.portable is True
    assert DataServices.portable is True
    laptop = Ctx(os=MAC, ex=FakeExecutor())
    assert DdevRemote().verify(laptop) is True  # a GUI Mac keeps ddev on localhost
    ssh = Ctx(os=MAC_SSH, ex=FakeExecutor())
    DdevRemote().install(ssh)
    assert _calls(ssh) == [["ddev", "config", "global", "--router-bind-all-interfaces"]]


def test_aspire_uses_the_user_dotnet(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    Aspire().install(ctx)
    dotnet = tmp_path / ".dotnet"
    assert _calls(ctx) == [[str(dotnet / "dotnet"), "tool", "install", "-g", "Aspire.Cli"]]
    assert ctx.ex.envs[0] == {"DOTNET_ROOT": str(dotnet)}  # type: ignore[attr-defined]


def test_aspire_force_updates_an_installed_tool(tmp_path: Path) -> None:
    tools = tmp_path / ".dotnet" / "tools"
    tools.mkdir(parents=True)
    (tools / "aspire").write_text("#!/bin/sh\n", encoding="utf-8")
    ctx = Ctx(os=MAC, ex=RuleExecutor(), force=True)
    assert Aspire().verify(ctx) is True
    Aspire().install(ctx)
    assert _calls(ctx)[0][1:] == ["tool", "update", "-g", "Aspire.Cli"]


def test_aspire_failure_is_reported() -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("tool",), Result(1))]))
    with pytest.raises(InstallError, match="Aspire.Cli"):
        Aspire().install(ctx)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_ddev_aspire_macos.py -v`
Expected: FAIL. `Ddev().install` on macOS falls to the Fedora branch (`dnf`) and `DdevRemote.portable` is `False`.

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/ddev.py`: add the imports `from dataclasses import dataclass`, `from devboost.core.errors import NeedsUser`, and above `class Ddev`:

```python
#: DDEV's own tap (auto-tapped by the fully qualified name) — DDEV's documented macOS path.
DDEV_FORMULA = "ddev/ddev/ddev"


@dataclass(frozen=True)
class _MacDdev:
    """macOS: brew the tap formula + mkcert, then trust mkcert's CA (spec §2, plan D18)."""

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, "ddev") and pkg.installed(ctx, "mkcert")

    def install(self, ctx: Ctx) -> None:
        wanted = ((DDEV_FORMULA, "ddev"), ("mkcert", "mkcert"))
        missing = [formula for formula, short in wanted if not pkg.installed(ctx, short)]
        if missing:
            pkg.install(ctx, *missing)
        if not ctx.ex.run(["mkcert", "-install"]).ok:
            raise NeedsUser(
                "mkcert could not add its local CA to the keychain",
                "run `mkcert -install` in a terminal (it asks for your password or a "
                "keychain approval), then re-run devboost",
            )
```

In `class Ddev`: `per_os = OsMap(macos=_MacDdev())`, plus the `os_strategy` hand-off as the first statement of `verify` and `install`, with the existing Linux bodies unchanged after it. (`OsMap` is already imported.)

In `class DdevRemote`: add `portable = True` with the comment `# ctx.os.headless is SSH-aware on macOS (M1); unchanged there`.

`engine/src/devboost/modules/dev_stacks.py`: add `from dataclasses import dataclass`, `from devboost.core.errors import InstallError`, `from devboost.core.osinfo import OsMap`. Above `class Aspire`:

```python
@dataclass(frozen=True)
class _MacAspire:
    """macOS: .NET lives in ~/.dotnet (dotnet-install.sh, spec §2) and is not on PATH
    inside this process, so call it by path with DOTNET_ROOT (plan D19)."""

    def verify(self, ctx: Ctx) -> bool:
        return (_home() / ".dotnet" / "tools" / "aspire").exists()

    def install(self, ctx: Ctx) -> None:
        dotnet = _home() / ".dotnet"
        verb = "update" if self.verify(ctx) else "install"  # `install` of a present tool fails
        argv = [str(dotnet / "dotnet"), "tool", verb, "-g", "Aspire.Cli"]
        res = ctx.ex.run(argv, env={"DOTNET_ROOT": str(dotnet)})
        if not res.ok:
            raise InstallError("aspire", f"dotnet tool {verb} -g Aspire.Cli", res.code)
```

In `class Aspire`: `per_os = OsMap(macos=_MacAspire())` and the `os_strategy` hand-off in `verify` and `install`. Skip this Aspire part if Task 0 found that M3 already resolved `aspire` (A3). In that case also delete `test_aspire_*` from the new test file.

In `class DataServices`: `portable = True` with the comment `# bundled compose file; postgres/valkey/dbgate images are multi-arch (spec §4)`.

`tests/core/test_macos_contract.py`: delete `"ddev"`, `"ddev-remote"`, `"data-services"` and (unless M3 did) `"aspire"` from `KNOWN_GAPS`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_ddev_aspire_macos.py tests/modules/test_docker_ddev.py tests/modules/test_dev_stacks.py tests/modules/test_ubuntu_dev_stacks.py tests/core/test_macos_contract.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. The Linux ddev/aspire tests are unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/ddev.py src/devboost/modules/dev_stacks.py \
  tests/modules/test_ddev_aspire_macos.py tests/core/test_macos_contract.py
git commit -m "feat(macos): ddev, Aspire and data-services on the Mac"
```

---

### Task 9: `LaunchdTimer` — aspire-gc and restic-backup on macOS

**Files:**
- Create: `engine/src/devboost/modules/_launchd_jobs.py`
- Modify: `engine/src/devboost/modules/dev_hygiene.py`, `engine/src/devboost/modules/system.py`, `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/modules/test_launchd_jobs.py` (create)

**Interfaces:**
- Consumes: Task 1 (`launchd.user_agent` with `log_path`, `launchd.agent_installed`), M1 `pkg`.
- Produces (module `devboost.modules._launchd_jobs`):
  - `Schedule = Literal["hourly", "daily"]`; `CALENDAR: dict[Schedule, dict[str, int]]` = `{"hourly": {"Minute": 0}, "daily": {"Hour": 0, "Minute": 0}}`.
  - `launchd_path() -> str`: `~/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`.
  - `log_path(name: str) -> Path`: `~/Library/Logs/devboost/<name>.log`.
  - `schedule_job(ctx, name: str, script: str, schedule: Schedule) -> bool`: agent `dev.devboost.<name>` running `/bin/sh -c <script>`.
  - `job_scheduled(ctx, name: str) -> bool`.
  - `@dataclass(frozen=True) class LaunchdTimer(name: str, script: str, schedule: Schedule, formulae: tuple[str, ...] = ())`, an `Installer`. `install` brews any missing formula, then schedules the job. `verify` requires every formula and the loaded job.

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_launchd_jobs.py`)

```python
from __future__ import annotations

import os
import plistlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer
from devboost.modules import _launchd_jobs as jobs
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.system import ResticBackup
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _plist(home: Path, name: str) -> dict[str, object]:
    path = home / "Library" / "LaunchAgents" / f"dev.devboost.{name}.plist"
    return plistlib.loads(path.read_bytes())  # type: ignore[no-any-return]


def test_launchd_path_puts_user_and_brew_bins_first(tmp_path: Path) -> None:
    assert jobs.launchd_path().split(":") == [
        str(tmp_path / ".local" / "bin"), "/opt/homebrew/bin", "/opt/homebrew/sbin",
        "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]


def test_schedule_job_writes_an_hourly_agent(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert jobs.schedule_job(ctx, "aspire-gc", "devboost dev gc", "hourly") is True
    data = _plist(tmp_path, "aspire-gc")
    assert data["Label"] == "dev.devboost.aspire-gc"
    assert data["ProgramArguments"] == ["/bin/sh", "-c", "devboost dev gc"]
    assert data["StartCalendarInterval"] == {"Minute": 0}
    assert data["EnvironmentVariables"] == {"PATH": jobs.launchd_path()}
    log = str(tmp_path / "Library" / "Logs" / "devboost" / "aspire-gc.log")
    assert data["StandardOutPath"] == log and data["StandardErrorPath"] == log
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.aspire-gc.plist"
    bootstrap = ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)]
    assert bootstrap in ctx.ex.calls  # type: ignore[attr-defined]


def test_daily_is_midnight_like_systemd(tmp_path: Path) -> None:
    jobs.schedule_job(Ctx(os=MAC, ex=FakeExecutor()), "x", "true", "daily")
    assert _plist(tmp_path, "x")["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}


def test_timer_is_an_installer_that_brews_what_it_needs() -> None:
    timer = jobs.LaunchdTimer("restic-backup", "exec restic snapshots", "daily", ("restic",))
    assert isinstance(timer, Installer)
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    timer.install(ctx)
    assert ["brew", "install", "--formula", "-y", "restic"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_timer_verify_needs_formula_and_loaded_job() -> None:
    timer = jobs.LaunchdTimer("t", "true", "hourly", ("restic",))
    ok = Ctx(os=MAC, ex=RuleExecutor())
    assert timer.verify(ok) is False  # no plist yet
    timer.install(ok)
    assert timer.verify(ok) is True
    no_formula = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    assert timer.verify(no_formula) is False
    unloaded = Ctx(os=MAC, ex=RuleExecutor(rules=[(("launchctl", "print"), Result(113))]))
    assert timer.verify(unloaded) is False


def test_aspire_gc_on_macos_is_an_hourly_agent(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    AspireGc().install(ctx)
    assert _plist(tmp_path, "aspire-gc")["ProgramArguments"] == [
        "/bin/sh", "-c", "devboost dev gc"
    ]
    assert not (tmp_path / ".config" / "systemd").exists()
    assert AspireGc().verify(ctx) is True


def test_restic_backup_on_macos_is_a_daily_agent_resolving_restic_via_path(
    tmp_path: Path,
) -> None:
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    ResticBackup().install(ctx)
    data = _plist(tmp_path, "restic-backup")
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    script = data["ProgramArguments"][2]  # type: ignore[index]
    assert script == 'exec restic backup --files-from "$HOME/.config/devboost/restic-include"'
    assert "/usr/bin/restic" not in script
    assert ResticBackup().verify(ctx) is True


def test_linux_timers_are_unchanged(tmp_path: Path) -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    AspireGc().install(ctx)
    assert (tmp_path / ".config" / "systemd" / "user" / "aspire-gc.timer").exists()
    assert not (tmp_path / "Library").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_launchd_jobs.py -v`
Expected: FAIL with `ImportError: cannot import name '_launchd_jobs'`.

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/_launchd_jobs.py`:

```python
"""Scheduled jobs on macOS — the launchd twin of dev-boost's systemd --user timers.

systemd ``OnCalendar=hourly|daily`` + ``Persistent=true`` maps to launchd
``StartCalendarInterval``: launchd runs a job whose time passed while the Mac slept once on
wake. A run missed while the Mac was powered off is not caught up — the one difference
(plan D5). Every job is ``/bin/sh -c <script>`` with an explicit PATH, since launchd starts
agents with a bare one, and logs to ``~/Library/Logs/devboost/<name>.log``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.exec.primitives import launchd, pkg
from devboost.model import Ctx

Schedule = Literal["hourly", "daily"]
#: The same wall-clock times as systemd's `hourly` (:00) and `daily` (00:00).
CALENDAR: dict[Schedule, dict[str, int]] = {
    "hourly": {"Minute": 0},
    "daily": {"Hour": 0, "Minute": 0},
}


def _home() -> Path:
    return Path(os.environ["HOME"])


def launchd_path() -> str:
    """PATH for agents: devboost's own bin, Homebrew, then the system dirs."""
    return ":".join([
        str(_home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ])


def log_path(name: str) -> Path:
    return _home() / "Library" / "Logs" / "devboost" / f"{name}.log"


def schedule_job(ctx: Ctx, name: str, script: str, schedule: Schedule) -> bool:
    """Install/refresh the ``dev.devboost.<name>`` agent. True when anything changed."""
    return launchd.user_agent(
        ctx,
        launchd.label(name),
        ["/bin/sh", "-c", script],
        start_calendar=CALENDAR[schedule],
        env={"PATH": launchd_path()},
        log_path=log_path(name),
    )


def job_scheduled(ctx: Ctx, name: str) -> bool:
    return launchd.agent_installed(ctx, launchd.label(name))


@dataclass(frozen=True)
class LaunchdTimer:
    """A ``per_os.macos`` strategy: brew ``formulae`` if missing, then schedule ``script``."""

    name: str
    script: str
    schedule: Schedule
    formulae: tuple[str, ...] = ()

    def verify(self, ctx: Ctx) -> bool:
        return all(pkg.installed(ctx, f) for f in self.formulae) and job_scheduled(
            ctx, self.name
        )

    def install(self, ctx: Ctx) -> None:
        missing = [f for f in self.formulae if not pkg.installed(ctx, f)]
        if missing:
            pkg.install(ctx, *missing)
        schedule_job(ctx, self.name, self.script, self.schedule)
```

`engine/src/devboost/modules/dev_hygiene.py`: import `from devboost.core.osinfo import OsMap` and `from devboost.modules._launchd_jobs import LaunchdTimer`. In `AspireGc`:

```python
    description = "Hourly GC of orphaned Aspire/dev containers (systemd timer / launchd agent)."
    per_os = OsMap(macos=LaunchdTimer("aspire-gc", "devboost dev gc", "hourly"))
```

Then add the `os_strategy` hand-off as the first statement of `verify` and `install`. The Linux bodies stay unchanged.

`engine/src/devboost/modules/system.py`: import `OsMap` (`from devboost.core.osinfo import OsMap`) and `LaunchdTimer`. In `ResticBackup`:

```python
    per_os = OsMap(
        macos=LaunchdTimer(
            "restic-backup",
            'exec restic backup --files-from "$HOME/.config/devboost/restic-include"',
            "daily",
            formulae=("restic",),
        )
    )
```

Add the `os_strategy` hand-off in `verify` and `install`.

`tests/core/test_macos_contract.py`: delete `"aspire-gc"` and `"restic-backup"` from `KNOWN_GAPS`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_launchd_jobs.py tests/modules/test_apps.py tests/modules/test_system.py tests/core/test_macos_contract.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_launchd_jobs.py src/devboost/modules/dev_hygiene.py \
  src/devboost/modules/system.py tests/modules/test_launchd_jobs.py \
  tests/core/test_macos_contract.py
git commit -m "feat(macos): aspire-gc and restic-backup as launchd agents on the same schedules"
```

---

### Task 10: restic-b2 and obsidian-sync on macOS

**Files:**
- Modify: `engine/src/devboost/modules/server.py`, `engine/src/devboost/modules/apps.py`, `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/modules/test_backup_vault_macos.py` (create)

**Interfaces:**
- Consumes: Task 9 (`schedule_job`, `job_scheduled`), M1 `secrets.age_key`.
- Produces:
  - `server._secret(ctx, field)` now decrypts through `age_key(ctx)` (D7).
  - `server._b2_prepare(ctx, *, shell_quoted: bool = False) -> Path | None`: writes `restic-include` (once) and a `0600` `restic-b2.env`, and returns the env file. Returns `None` (after the existing warning) when a secret is missing.
  - `server.B2_MAC_SCRIPT: str`; `ResticB2.per_os.macos` (`_MacResticB2`).
  - `apps._provision_vault(ctx) -> Path | None` (the existing provisioning moved out of `ObsidianSync.install`) and `apps._ssh_alias(ctx, key)` (moved from the method, same body); `ObsidianSync.per_os.macos` (`_MacObsidianSync`).

- [ ] **Step 1: Write the failing tests** (`tests/modules/test_backup_vault_macos.py`)

```python
from __future__ import annotations

import plistlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import apps, server
from devboost.modules.apps import ObsidianSync
from devboost.modules.server import B2_MAC_SCRIPT, ResticB2
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
SECRETS = {
    "B2_ACCOUNT_ID": "id",
    "B2_ACCOUNT_KEY": "key",
    "RESTIC_REPOSITORY": "b2:bucket:path",
    "RESTIC_PASSWORD": "p w$1",
}


def _plist(home: Path, name: str) -> dict[str, object]:
    path = home / "Library" / "LaunchAgents" / f"dev.devboost.{name}.plist"
    return plistlib.loads(path.read_bytes())  # type: ignore[no-any-return]


# ── restic-b2 ────────────────────────────────────────────────────────────────
def test_restic_b2_on_macos_schedules_a_nightly_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: SECRETS.get(f))
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    ResticB2().install(ctx)
    data = _plist(tmp_path, "restic-b2")
    assert data["ProgramArguments"] == ["/bin/sh", "-c", B2_MAC_SCRIPT]
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    env = tmp_path / ".config" / "devboost" / "restic-b2.env"
    assert "RESTIC_PASSWORD='p w$1'\n" in env.read_text(encoding="utf-8")  # sh-sourceable
    assert oct(env.stat().st_mode)[-3:] == "600"
    assert (tmp_path / ".config" / "devboost" / "restic-include").exists()
    assert not any("systemctl" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]
    assert ResticB2().verify(ctx) is True


def test_b2_mac_script_matches_the_linux_unit_semantics() -> None:
    assert B2_MAC_SCRIPT.startswith('set -a; . "$HOME/.config/devboost/restic-b2.env"; set +a; ')
    assert "restic init >/dev/null 2>&1; " in B2_MAC_SCRIPT  # like ExecStartPre=-
    assert (
        'restic backup --files-from "$HOME/.config/devboost/restic-include" && '
        "restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune"
    ) in B2_MAC_SCRIPT  # ExecStartPost only after a successful ExecStart
    assert "/usr/bin/restic" not in B2_MAC_SCRIPT


def test_restic_b2_on_macos_without_secrets_wires_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: None)
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    ResticB2().install(ctx)
    assert ["brew", "install", "--formula", "-y", "restic"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert not (tmp_path / "Library" / "LaunchAgents").exists()


def test_linux_env_file_format_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: SECRETS.get(f))
    envfile = server._b2_prepare(Ctx(os=FEDORA, ex=FakeExecutor()))
    assert envfile is not None
    assert envfile.read_text(encoding="utf-8") == (
        "B2_ACCOUNT_ID=id\nB2_ACCOUNT_KEY=key\n"
        "RESTIC_REPOSITORY=b2:bucket:path\nRESTIC_PASSWORD=p w$1\n"
    )


def test_secret_decrypts_with_the_keychain_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "materialized-key"
    seen: list[Path] = []

    @contextmanager
    def fake_age_key(ctx: Ctx) -> Iterator[Path | None]:
        yield key

    def fake_decrypt(ctx: Ctx, bundle: Path, k: Path) -> dict[str, str]:
        seen.append(k)
        return {"B2_ACCOUNT_ID": "id"}

    monkeypatch.setattr(server, "age_key", fake_age_key)
    monkeypatch.setattr(server.age, "decrypt", fake_decrypt)
    assert server._secret(Ctx(os=MAC, ex=FakeExecutor()), "B2_ACCOUNT_ID") == "id"
    assert seen == [key]


def test_secret_is_none_without_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def no_key(ctx: Ctx) -> Iterator[Path | None]:
        yield None

    monkeypatch.setattr(server, "age_key", no_key)
    assert server._secret(Ctx(os=MAC, ex=FakeExecutor()), "B2_ACCOUNT_ID") is None


# ── obsidian-sync ────────────────────────────────────────────────────────────
def _vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "Vault"
    monkeypatch.setenv("VAULT_DIR", str(vault))
    monkeypatch.setenv("DEVBOOST_VAULT_REPO", "notes")
    (tmp_path / ".ssh").mkdir(mode=0o700)
    (tmp_path / ".ssh" / "devboost-vault").write_text("priv", encoding="utf-8")
    (tmp_path / ".ssh" / "devboost-vault.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")
    monkeypatch.setattr(
        apps.creds_src, "github_credentials",
        lambda ctx: {"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "p"},
    )
    monkeypatch.setattr(apps.github, "add_deploy_key", lambda *a, **k: True)
    return vault


def test_obsidian_sync_on_macos_is_a_daily_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault_env(tmp_path, monkeypatch)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    ObsidianSync().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["git", "clone", "git@devboost-vault.github.com:alice/notes.git", str(vault)] in calls
    data = _plist(tmp_path, "obsidian-sync")
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    assert data["ProgramArguments"] == [
        "/bin/sh", "-c",
        f"cd {vault} && git add -A && git commit -m auto >/dev/null 2>&1; "
        "git pull --rebase && git push",
    ]
    assert not any("systemctl" in c for c in calls)
    (vault / ".git").mkdir(parents=True)
    assert ObsidianSync().verify(ctx) is True


def test_obsidian_sync_on_macos_skips_without_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_VAULT_REPO", raising=False)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    ObsidianSync().install(ctx)
    assert ctx.ex.calls == []  # type: ignore[attr-defined]
    assert ObsidianSync().verify(ctx) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_backup_vault_macos.py -v`
Expected: FAIL with `ImportError: cannot import name 'B2_MAC_SCRIPT'`.

- [ ] **Step 3: Implement `server.py`**

Imports: add `import shlex`, `from dataclasses import dataclass`, `from devboost.core.osinfo import OsMap`, `from devboost.modules._launchd_jobs import job_scheduled, schedule_job`, and change the secrets import to `from devboost.modules.secrets import age_key, bundle_path`. `key_path` is no longer used here; remove it only if nothing else in the file uses it.

Replace `_secret`:

```python
def _secret(ctx: Ctx, field: str) -> str | None:
    """Read one field from the age secrets bundle, or None if unavailable.

    Server modules must not fail `devboost server` just because an optional secret
    (a Tailscale auth key, B2 credentials) wasn't provisioned — they degrade to a
    printed next-step instead. The key comes from `age_key`: the key file, or on macOS the
    login keychain (M1); off macOS it is exactly the configured key path, as before.
    """
    with age_key(ctx) as key:
        if key is None:
            return None
        try:
            data = age.decrypt(ctx, bundle_path(), key)
        except SecretsError:
            return None
    return data.get(field)
```

Add above `class ResticB2`:

```python
_B2_FIELDS = ("B2_ACCOUNT_ID", "B2_ACCOUNT_KEY", "RESTIC_REPOSITORY", "RESTIC_PASSWORD")

#: The macOS job: the Linux unit's ExecStartPre=- / ExecStart / ExecStartPost, in sh.
B2_MAC_SCRIPT = (
    'set -a; . "$HOME/.config/devboost/restic-b2.env"; set +a; '
    "restic init >/dev/null 2>&1; "
    'restic backup --files-from "$HOME/.config/devboost/restic-include" && '
    "restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune"
)


def _b2_prepare(ctx: Ctx, *, shell_quoted: bool = False) -> Path | None:
    """Write restic-include (once) and the 0600 env file; None when a secret is missing.

    ``shell_quoted`` quotes values for ``sh`` to source (macOS); systemd's
    EnvironmentFile format (Linux) is unchanged.
    """
    values: dict[str, str] = {}
    for field in _B2_FIELDS:
        value = _secret(ctx, field)
        if not value:
            log.warn(
                "restic-b2: installed restic, but B2/restic secrets are missing — add "
                "B2_ACCOUNT_ID, B2_ACCOUNT_KEY, RESTIC_REPOSITORY, RESTIC_PASSWORD to the "
                "secrets bundle to enable the nightly timer"
            )
            return None
        values[field] = value
    d = _devboost_dir()
    d.mkdir(parents=True, exist_ok=True)
    include = d / "restic-include"
    if not include.exists():  # editable default; keep what the user tuned
        home = Path(os.environ["HOME"])
        include.write_text(f"{home}/repos\n{home}/.config\n", encoding="utf-8")
    envfile = d / "restic-b2.env"
    envfile.touch(mode=0o600, exist_ok=True)
    envfile.chmod(0o600)  # before the secrets land in it
    envfile.write_text(
        "".join(
            f"{k}={shlex.quote(v) if shell_quoted else v}\n" for k, v in values.items()
        ),
        encoding="utf-8",
    )
    return envfile


@dataclass(frozen=True)
class _MacResticB2:
    """macOS: brew restic; with secrets, a nightly launchd agent (plan D7)."""

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, "restic") and job_scheduled(ctx, "restic-b2")

    def install(self, ctx: Ctx) -> None:
        if not pkg.installed(ctx, "restic"):
            pkg.install(ctx, "restic")
        if _b2_prepare(ctx, shell_quoted=True) is None:
            return
        schedule_job(ctx, "restic-b2", B2_MAC_SCRIPT, "daily")
```

`ResticB2` gets `per_os = OsMap(macos=_MacResticB2())`, and `description` changes to `"Offsite encrypted backups — restic → Backblaze B2, nightly (systemd timer / launchd agent)."`. The `os_strategy` hand-off goes first in `verify` and `install`. The Linux `install` body becomes:

```python
        if not ctx.ex.which("restic"):
            pkg.install(ctx, "restic")
        # Destination + credentials come from the age bundle. Without them we can't run an
        # offsite backup, so install the binary and stop — don't wire a timer to nowhere.
        envfile = _b2_prepare(ctx)
        if envfile is None:
            return
        include = envfile.parent / "restic-include"
        service = (
            "[Unit]\nDescription=devboost restic → B2 backup\n\n[Service]\nType=oneshot\n"
            f"EnvironmentFile={envfile}\n"
            "ExecStartPre=-/usr/bin/restic init\n"  # no-op once the repo exists
            f"ExecStart=/usr/bin/restic backup --files-from {include}\n"
            "ExecStartPost=/usr/bin/restic forget --keep-daily 7 --keep-weekly 4 "
            "--keep-monthly 6 --prune\n"
        )
        timer = (
            "[Unit]\nDescription=nightly restic → B2\n\n[Timer]\nOnCalendar=daily\n"
            "Persistent=true\n\n[Install]\nWantedBy=timers.target\n"
        )
        systemd.write_user_unit(ctx, "restic-b2.service", service)
        systemd.write_user_unit(ctx, "restic-b2.timer", timer)
        systemd.enable_user_unit(ctx, "restic-b2.timer", now=True)
```

The unit text is unchanged; only the secret/env-file lines moved into `_b2_prepare`.

- [ ] **Step 4: Implement `apps.py`**

Imports: add `import shlex`, `from dataclasses import dataclass`, `from devboost.core.osinfo import OsMap`, `from devboost.modules._launchd_jobs import job_scheduled, schedule_job`.

Move the body of `ObsidianSync.install` up to and including the clone into a module-level function, and `_ssh_alias` out of the class (same body, `self` dropped):

```python
def _ssh_alias(ctx: Ctx, key: Path) -> None:
    cfg = _home() / ".ssh" / "config"
    block = (
        f"\nHost {_SSH_ALIAS}\n  HostName github.com\n  User git\n"
        f"  IdentityFile {key}\n  IdentitiesOnly yes\n"
    )
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if _SSH_ALIAS not in text:
        cfg.write_text(text + block, encoding="utf-8")


def _provision_vault(ctx: Ctx) -> Path | None:
    """Deploy key, SSH alias, clone. The vault dir, or None when skipped (non-blocking)."""
    repo = os.environ.get("DEVBOOST_VAULT_REPO")
    if not repo:
        log.warn("obsidian-sync: DEVBOOST_VAULT_REPO not set — skipping (non-blocking)")
        return None
    creds = creds_src.github_credentials(ctx)
    if creds is None:
        log.warn(
            "obsidian-sync: no GitHub credentials found (bundle, gh, git credentials) "
            "— skipping (non-blocking)"
        )
        return None
    owner, pat = creds["GIT_USER"], creds["GITHUB_PAT"]

    key = _home() / _DEPLOY_KEY
    if not key.exists():
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        ctx.ex.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C",
                    f"devboost-vault:{socket.gethostname()}", "-f", str(key)])
    _ssh_alias(ctx, key)

    pub = key.with_suffix(".pub")
    if pub.exists():
        try:
            github.add_deploy_key(pat, owner, repo, pub.read_text(encoding="utf-8"),
                                  f"devboost-vault:{socket.gethostname()}")
        except GithubError:
            log.warn("obsidian-sync: deploy-key registration failed (non-blocking)")
            return None

    vault = _vault_dir()
    if not (vault / ".git").is_dir():
        ctx.ex.run(["git", "clone", f"git@{_SSH_ALIAS}:{owner}/{repo}.git", str(vault)])
    return vault


@dataclass(frozen=True)
class _MacObsidianSync:
    """macOS: the same provisioning, with the daily push as a launchd agent (plan D5)."""

    def verify(self, ctx: Ctx) -> bool:
        return (_vault_dir() / ".git").is_dir() and job_scheduled(ctx, "obsidian-sync")

    def install(self, ctx: Ctx) -> None:
        vault = _provision_vault(ctx)
        if vault is None:
            return
        script = (
            f"cd {shlex.quote(str(vault))} && git add -A && "
            "git commit -m auto >/dev/null 2>&1; git pull --rebase && git push"
        )
        schedule_job(ctx, "obsidian-sync", script, "daily")
```

`ObsidianSync` then becomes:

```python
    per_os = OsMap(macos=_MacObsidianSync())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return (_vault_dir() / ".git").is_dir()

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        vault = _provision_vault(ctx)
        if vault is not None:
            self._systemd_backstop(ctx, vault)
```

`_systemd_backstop` is unchanged.

`tests/core/test_macos_contract.py`: delete `"restic-b2"` and `"obsidian-sync"` from `KNOWN_GAPS`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_backup_vault_macos.py tests/modules/test_server.py tests/modules/test_apps.py tests/core/test_macos_contract.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. The existing Linux tests (`test_restic_b2_*`, `test_obsidian_sync_provisions`) pass unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/server.py src/devboost/modules/apps.py \
  tests/modules/test_backup_vault_macos.py tests/core/test_macos_contract.py
git commit -m "feat(macos): restic-b2 and obsidian-sync as launchd agents; keychain age key"
```

---

### Task 11: browser-mcp on macOS

**Files:**
- Create: `engine/src/devboost/modules/browser_mcp.py`
- Modify: `dotfiles/dot_local/bin/executable_browser-mcp`, `profiles.toml`
- Test: `engine/tests/modules/test_browser_mcp.py`, `engine/tests/dotfiles/test_browser_mcp_launcher.py` (create)

**Interfaces:**
- Consumes: Task 1 (`user_agent` with `keep_alive`/`throttle_interval`/`log_path`, `agent_installed`), Task 9 (`launchd_path`, `log_path`), `Dotfiles` (`devboost.modules.shell`).
- Produces: module `browser-mcp` (`families = ("macos",)`, profile `remote`, `gui = True`, `requires = (Dotfiles,)`), with LaunchAgent `dev.devboost.browser-mcp`. The launcher honours `CHROME_APP` (default `/Applications/Google Chrome.app`).

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_browser_mcp.py`:

```python
from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules._launchd_jobs import launchd_path
from devboost.modules.browser_mcp import BrowserMcp

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _launcher(home: Path) -> Path:
    p = home / ".local" / "bin" / "browser-mcp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return p


def test_runs_the_dotfiles_launcher_as_a_keep_alive_agent(tmp_path: Path) -> None:
    launcher = _launcher(tmp_path)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    BrowserMcp().install(ctx)
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.browser-mcp.plist"
    data = plistlib.loads(plist.read_bytes())
    assert data["ProgramArguments"] == [str(launcher)]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 60
    shims = str(tmp_path / ".local" / "share" / "mise" / "shims")
    assert data["EnvironmentVariables"] == {"PATH": f"{shims}:{launchd_path()}"}
    assert BrowserMcp().verify(ctx) is True


def test_missing_launcher_points_at_the_dotfiles() -> None:
    with pytest.raises(ConfigError, match="devboost install dotfiles"):
        BrowserMcp().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert BrowserMcp().verify(Ctx(os=MAC, ex=FakeExecutor())) is False


def test_metadata() -> None:
    assert BrowserMcp.families == ("macos",)
    assert BrowserMcp.profiles == ("remote",)
    assert BrowserMcp.gui is True
    assert [c.name for c in BrowserMcp.requires] == ["dotfiles"]


def test_linux_plans_drop_it(tmp_path: Path) -> None:
    plan = build_plan(["browser-mcp"], load(), FEDORA, gpu_marker=tmp_path / "none")
    assert [p.name for p in plan] == []
    mac = build_plan(["browser-mcp"], load(), MAC, gpu_marker=tmp_path / "none")
    assert [(p.name, p.skip_reason) for p in mac] == [("browser-mcp", None)]
```

`tests/dotfiles/test_browser_mcp_launcher.py`:

```python
"""The browser-mcp launcher picks Chrome on macOS (CHROME_APP) without a PATH binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LAUNCHER = (
    Path(__file__).resolve().parents[3] / "dotfiles" / "dot_local" / "bin"
    / "executable_browser-mcp"
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def _fake_bin(tmp_path: Path) -> Path:
    """PATH holds only fakes + `head`, so a google-chrome on the host (CI images ship one)
    cannot leak into the channel choice."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "tailscale").write_text("#!/bin/sh\necho 100.64.0.7\n", encoding="utf-8")
    (bin_ / "npx").write_text('#!/bin/sh\necho "$@"\n', encoding="utf-8")
    for f in bin_.iterdir():
        f.chmod(0o755)
    head = shutil.which("head")
    assert head is not None
    (bin_ / "head").symlink_to(head)
    return bin_


def _run(tmp_path: Path, chrome_app: Path) -> str:
    bash = shutil.which("bash")
    assert bash is not None
    env = {"HOME": str(tmp_path), "PATH": str(_fake_bin(tmp_path)), "CHROME_APP": str(chrome_app)}
    out = subprocess.run(
        [bash, str(LAUNCHER)], env=env, capture_output=True, text=True, check=True
    )
    return out.stdout


def test_chrome_app_bundle_selects_the_chrome_channel(tmp_path: Path) -> None:
    app = tmp_path / "Google Chrome.app"
    app.mkdir()
    assert "--browser chrome" in _run(tmp_path, app)


def test_no_chrome_falls_back_to_chromium(tmp_path: Path) -> None:
    out = _run(tmp_path, tmp_path / "absent.app")
    assert "--browser chromium" in out
    assert "--host 100.64.0.7" in out and "--allowed-hosts 100.64.0.7:8931" in out


def test_launcher_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(LAUNCHER)], check=True, env=dict(os.environ))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_browser_mcp.py tests/dotfiles/test_browser_mcp_launcher.py -v`
Expected: `test_browser_mcp.py` FAILS with `ModuleNotFoundError: No module named 'devboost.modules.browser_mcp'`. `test_chrome_app_bundle_selects_the_chrome_channel` FAILS (it prints `--browser chromium`). The other two launcher tests PASS.

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/browser_mcp.py`:

```python
"""browser-mcp on macOS — keep the Playwright MCP launcher running as a LaunchAgent.

On Linux the dotfiles own this (a systemd --user unit that chezmoi enables; see
dotfiles/dot_config/systemd/user/README.md), so there is no engine module there. A dotfile
cannot load a launchd job, hence this macOS-only module (spec §2, plan D9).
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import ConfigError
from devboost.core.registry import register
from devboost.exec.primitives import launchd
from devboost.model import Ctx, Module
from devboost.modules._launchd_jobs import launchd_path, log_path
from devboost.modules.shell import Dotfiles

_NAME = "browser-mcp"


def _home() -> Path:
    return Path(os.environ["HOME"])


def _launcher() -> Path:
    return _home() / ".local" / "bin" / "browser-mcp"


@register
class BrowserMcp(Module):
    name = "browser-mcp"
    category = "remote"
    description = "Playwright MCP on the tailnet for remote Claude Code sessions (launchd agent)."
    families = ("macos",)
    requires = (Dotfiles,)
    profiles = ("remote",)
    gui = True

    def verify(self, ctx: Ctx) -> bool:
        return _launcher().exists() and launchd.agent_installed(ctx, launchd.label(_NAME))

    def install(self, ctx: Ctx) -> None:
        if not _launcher().exists():
            raise ConfigError(
                f"{_launcher()} is missing — run: devboost install dotfiles"
            )
        # npx comes from mise's shims, first on PATH — as in the systemd unit.
        shims = _home() / ".local" / "share" / "mise" / "shims"
        launchd.user_agent(
            ctx,
            launchd.label(_NAME),
            [str(_launcher())],
            run_at_load=True,
            # Restart after a failure only (≈ Restart=on-failure); once a minute while the
            # tailnet is down rather than launchd's default every 10 s.
            keep_alive={"SuccessfulExit": False},
            throttle_interval=60,
            env={"PATH": f"{shims}:{launchd_path()}"},
            log_path=log_path(_NAME),
        )
```

In `dotfiles/dot_local/bin/executable_browser-mcp`, replace the channel block:

```bash
BROWSER_CHANNEL="${BROWSER_CHANNEL:-}"
CHROME_APP="${CHROME_APP:-/Applications/Google Chrome.app}"
if [ -z "${BROWSER_CHANNEL}" ]; then
  if command -v google-chrome >/dev/null 2>&1 \
    || command -v google-chrome-stable >/dev/null 2>&1 \
    || [ -d "${CHROME_APP}" ]; then
    BROWSER_CHANNEL=chrome
  else
    BROWSER_CHANNEL=chromium
  fi
fi
```

and in the header comment, change `# Normally started by the systemd user unit (see ../../config/systemd/user/).` to

```bash
# Normally started by the systemd user unit on Linux (see ../../config/systemd/user/) and
# by the dev.devboost.browser-mcp LaunchAgent on macOS (devboost install browser-mcp).
```

`profiles.toml`: append `"browser-mcp"` to the `remote` line as Task 0 recorded it, e.g. `remote = ["tailscale","mosh","browser-mcp"]`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_browser_mcp.py tests/dotfiles/ tests/core/ -v && uv run mypy && uv run ruff check && shellcheck ../dotfiles/dot_local/bin/executable_browser-mcp`
Expected: PASS, clean. `test_no_new_macos_gaps` stays green because `families = ("macos",)` makes the new module resolvable.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/browser_mcp.py tests/modules/test_browser_mcp.py \
  tests/dotfiles/test_browser_mcp_launcher.py ../dotfiles/dot_local/bin/executable_browser-mcp \
  ../profiles.toml
git commit -m "feat(macos): browser-mcp LaunchAgent; launcher finds Chrome.app"
```

---

### Task 12: `devboost docker use <runtime>`

**Files:**
- Create: `engine/src/devboost/modules/_docker_switch.py`, `engine/src/devboost/cli/docker_cmd.py`
- Modify: `engine/src/devboost/cli/app.py`
- Test: `engine/tests/modules/test_docker_switch.py`, `engine/tests/cli/test_docker_cmd.py` (create)

**Interfaces:**
- Consumes: Tasks 3, 4, 7 (`selected_docker_runtime`, `set_user_value`, `runtime_for`, `use_context`, `license_note`, `BUILDER_GC`), `registry.load`, `cli/host.mac_session`.
- Produces:
  - `_docker_switch.REVERIFY = ("docker", "docker-build-gc", "aspire-gc", "ddev", "data-services")`, `REQUIRED = frozenset({"docker", "docker-build-gc"})`.
  - `@dataclass(frozen=True) class SwitchReport(previous: DockerRuntimeName, target: DockerRuntimeName, checks: tuple[tuple[str, bool], ...])` with the property `ok: bool` (every `REQUIRED` check passed).
  - `switch_runtime(ctx, target: DockerRuntimeName, *, snapshot: bool) -> SwitchReport` (spec §4 steps 1–5; D17).
  - CLI: `devboost docker use RUNTIME [--snapshot/--no-snapshot] [--yes/-y]`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_docker_switch.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import DockerRuntimeName, load_user_config, set_user_value
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules import _docker_switch as sw
from devboost.modules.docker import BUILDER_GC

MAC = OsInfo("macos", "macos", "aarch64")


class _Rt:
    """Records each call as `rt <name> <method>` on the executor, so order is checkable."""

    def __init__(
        self, name: DockerRuntimeName, *, installed: bool = True, merged: bool = True,
        fail_start: bool = False,
    ) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._installed, self._merged, self._fail_start = installed, merged, fail_start

    def _rec(self, ctx: Ctx, what: str) -> None:
        ctx.ex.run(["rt", self.name, what])

    def daemon_config_path(self) -> Path:
        return Path("/nonexistent")

    def installed(self, ctx: Ctx) -> bool:
        return self._installed

    def install(self, ctx: Ctx) -> None:
        self._rec(ctx, "install")

    def configure(self, ctx: Ctx) -> None:
        self._rec(ctx, "configure")

    def start(self, ctx: Ctx) -> None:
        self._rec(ctx, "start")
        if self._fail_start:
            raise NeedsUser("first launch", "open the app")

    def stop(self, ctx: Ctx) -> None:
        self._rec(ctx, "stop")

    def disable_autostart(self, ctx: Ctx) -> None:
        self._rec(ctx, "disable_autostart")

    def release_socket(self, ctx: Ctx) -> None:
        self._rec(ctx, "release_socket")

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        assert patch == BUILDER_GC
        self._rec(ctx, "merge_daemon_config")
        return self._merged

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return True

    def restart_engine(self, ctx: Ctx) -> None:
        self._rec(ctx, "restart_engine")

    def verify(self, ctx: Ctx) -> bool:
        return True


@pytest.fixture
def runtimes(monkeypatch: pytest.MonkeyPatch) -> dict[str, _Rt]:
    table = {"colima": _Rt("colima"), "orbstack": _Rt("orbstack"),
             "docker-desktop": _Rt("docker-desktop")}
    monkeypatch.setattr(sw, "runtime_for", lambda name: table[name])
    monkeypatch.setattr(sw, "_verify", lambda ctx, name: True)
    return table


def _mac(present: set[str] | None = None, **scripts: Result) -> Ctx:
    return Ctx(os=MAC, ex=FakeExecutor(present=present if present is not None else {"ddev"},
                                       scripts=dict(scripts)))


def test_colima_to_orbstack_runs_the_spec_steps_in_order(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac()
    report = sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["ddev", "snapshot", "--all"],
        ["ddev", "poweroff"],
        ["rt", "colima", "stop"],
        ["rt", "colima", "disable_autostart"],
        ["rt", "colima", "release_socket"],
        ["rt", "orbstack", "install"],
        ["rt", "orbstack", "configure"],
        ["rt", "orbstack", "start"],
        ["docker", "context", "use", "ctx-orbstack"],
        ["rt", "orbstack", "merge_daemon_config"],
        ["rt", "orbstack", "restart_engine"],
    ]
    assert load_user_config().docker_runtime == "orbstack"
    assert report.previous == "colima" and report.target == "orbstack"
    assert [n for n, _ in report.checks] == list(sw.REVERIFY)
    assert report.ok is True


def test_no_snapshot_still_powers_ddev_off(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac()
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ctx.ex.calls[0] == ["ddev", "poweroff"]  # type: ignore[attr-defined]


def test_without_ddev_there_is_nothing_to_snapshot(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert not any(c[0] == "ddev" for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_failed_snapshot_aborts_before_touching_the_old_runtime(
    runtimes: dict[str, _Rt],
) -> None:
    ctx = _mac(ddev=Result(1))
    with pytest.raises(InstallError, match="ddev snapshot --all"):
        sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert ctx.ex.calls == [["ddev", "snapshot", "--all"]]  # type: ignore[attr-defined]
    assert load_user_config().docker_runtime is None


def test_same_runtime_reconfigures_without_stopping(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "colima", snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["rt", "colima", "stop"] not in calls
    assert ["rt", "colima", "configure"] in calls


def test_an_uninstalled_old_runtime_is_not_stopped(
    runtimes: dict[str, _Rt], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtimes["colima"] = _Rt("colima", installed=False)
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ["rt", "colima", "stop"] not in ctx.ex.calls  # type: ignore[attr-defined]


def test_blocked_new_runtime_leaves_the_saved_choice_alone(runtimes: dict[str, _Rt]) -> None:
    set_user_value("docker_runtime", "colima")
    runtimes["orbstack"] = _Rt("orbstack", fail_start=True)
    with pytest.raises(NeedsUser):
        sw.switch_runtime(_mac(present=set()), "orbstack", snapshot=False)
    assert load_user_config().docker_runtime == "colima"


def test_unchanged_daemon_config_needs_no_restart(runtimes: dict[str, _Rt]) -> None:
    runtimes["orbstack"] = _Rt("orbstack", merged=False)
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ["rt", "orbstack", "restart_engine"] not in ctx.ex.calls  # type: ignore[attr-defined]


def test_report_ok_only_needs_docker_and_build_gc() -> None:
    ok = sw.SwitchReport("colima", "orbstack", (("docker", True), ("docker-build-gc", True),
                                                 ("ddev", False)))
    assert ok.ok is True
    bad = sw.SwitchReport("colima", "orbstack", (("docker", False), ("docker-build-gc", True)))
    assert bad.ok is False


class _Boom(Module):
    name: ClassVar[str] = "boom-probe"

    def verify(self, ctx: Ctx) -> bool:
        raise InstallError("boom", "x", 1)

    def install(self, ctx: Ctx) -> None:
        return None


def test_verify_helper_is_false_for_unknown_or_failing_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sw, "load", lambda: {"boom-probe": _Boom})
    ctx = _mac()
    assert sw._verify(ctx, "boom-probe") is False
    assert sw._verify(ctx, "no-such-module") is False
```

`tests/cli/test_docker_cmd.py`:

```python
from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import pytest
from typer.testing import CliRunner

from devboost.cli import docker_cmd
from devboost.cli.app import app
from devboost.core import osinfo
from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.modules._docker_switch import SwitchReport

MAC = OsInfo("macos", "macos", "aarch64")
runner = CliRunner()


@pytest.fixture
def on_mac(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(osinfo, "detect", lambda *a, **k: MAC)
    monkeypatch.setattr(docker_cmd, "RealExecutor", lambda: FakeExecutor(present={"ddev"}))
    monkeypatch.setattr(docker_cmd.plat, "mac_session", lambda os_info, dry_run: nullcontext())

    def fake_switch(ctx: Any, target: str, *, snapshot: bool) -> SwitchReport:
        seen.append({"target": target, "snapshot": snapshot})
        return SwitchReport("colima", target,  # type: ignore[arg-type]
                            (("docker", True), ("docker-build-gc", True), ("ddev", False)))

    monkeypatch.setattr(docker_cmd, "switch_runtime", fake_switch)
    return seen


def test_use_is_macos_only() -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack"])
    assert res.exit_code == 2
    assert "macOS-only" in res.output


def test_use_rejects_an_unknown_runtime(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "podman"])
    assert res.exit_code == 2
    assert "unknown docker runtime 'podman'" in res.output
    assert on_mac == []


def test_use_with_yes_snapshots(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack", "--yes"])
    assert res.exit_code == 0, res.output
    assert on_mac == [{"target": "orbstack", "snapshot": True}]
    assert "ddev" in res.output and "devboost install ddev" in res.output


def test_use_no_snapshot_flag(on_mac: list[dict[str, Any]]) -> None:
    runner.invoke(app, ["docker", "use", "orbstack", "--no-snapshot"])
    assert on_mac == [{"target": "orbstack", "snapshot": False}]


def test_use_asks_when_not_told(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack"], input="n\n")
    assert "ddev snapshot --all" in res.output
    assert on_mac == [{"target": "orbstack", "snapshot": False}]


def test_blocked_switch_prints_the_fix_and_the_way_back(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(ctx: Any, target: str, *, snapshot: bool) -> SwitchReport:
        raise NeedsUser("OrbStack has not finished its first launch", "open -a OrbStack")

    monkeypatch.setattr(docker_cmd, "switch_runtime", blocked)
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
    assert "open -a OrbStack" in res.output
    assert "devboost docker use colima" in res.output


def test_failed_required_check_exits_1(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        docker_cmd, "switch_runtime",
        lambda ctx, target, *, snapshot: SwitchReport("colima", target, (("docker", False),)),
    )
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_docker_switch.py tests/cli/test_docker_cmd.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._docker_switch'`.

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/_docker_switch.py`:

```python
"""Move this Mac to another Docker runtime — `devboost docker use` (spec §4, plan D17)."""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core import log
from devboost.core.errors import DevbootError, InstallError
from devboost.core.registry import load
from devboost.core.settings import Settings
from devboost.core.userconfig import DockerRuntimeName, selected_docker_runtime, set_user_value
from devboost.model import Ctx
from devboost.modules._docker_runtime import license_note, runtime_for, use_context
from devboost.modules.docker import BUILDER_GC

#: Re-verified after a switch (spec §4 step 5). The first two are what the switch itself
#: sets up; the others may legitimately not be installed on this Mac.
REVERIFY: tuple[str, ...] = ("docker", "docker-build-gc", "aspire-gc", "ddev", "data-services")
REQUIRED: frozenset[str] = frozenset({"docker", "docker-build-gc"})


@dataclass(frozen=True)
class SwitchReport:
    previous: DockerRuntimeName
    target: DockerRuntimeName
    checks: tuple[tuple[str, bool], ...]

    @property
    def ok(self) -> bool:
        return all(passed for name, passed in self.checks if name in REQUIRED)


def _verify(ctx: Ctx, name: str) -> bool:
    cls = load().get(name)
    if cls is None:
        return False
    try:
        return cls().verify(ctx)
    except DevbootError:
        return False


def _snapshot_and_poweroff(ctx: Ctx, *, snapshot: bool) -> None:
    """Steps 1–2: ddev databases live in the old runtime's VM — snapshot, then stop."""
    if not ctx.ex.which("ddev"):
        return
    if snapshot:
        res = ctx.ex.run(["ddev", "snapshot", "--all"])
        if not res.ok:
            raise InstallError("ddev", "ddev snapshot --all", res.code)
    ctx.ex.run(["ddev", "poweroff"])


def switch_runtime(ctx: Ctx, target: DockerRuntimeName, *, snapshot: bool) -> SwitchReport:
    """Stop the current runtime, bring up ``target``, save the choice, re-verify.

    Choosing the current runtime again re-runs every configure step (a repair). A failure
    before the last step leaves config.toml naming the previous runtime.
    """
    previous = selected_docker_runtime()
    _snapshot_and_poweroff(ctx, snapshot=snapshot)
    old = runtime_for(previous)
    if previous != target and old.installed(ctx):  # step 3 — stopped, not uninstalled
        old.stop(ctx)
        old.disable_autostart(ctx)
        old.release_socket(ctx)
    new = runtime_for(target)  # step 4
    note = license_note(target)
    if note:
        log.warn(f"docker: {target} — {note}")
    new.install(ctx)
    new.configure(ctx)
    new.start(ctx)
    use_context(ctx, new.context_name)
    if new.merge_daemon_config(ctx, BUILDER_GC):
        new.restart_engine(ctx)
    set_user_value("docker_runtime", target)  # step 5
    env = Settings().docker_runtime
    if env and env != target:
        log.warn(
            f"DEVBOOST_DOCKER_RUNTIME={env} is set and overrides the saved choice — "
            f"unset it to use {target}"
        )
    return SwitchReport(previous, target, tuple((n, _verify(ctx, n)) for n in REVERIFY))
```

`engine/src/devboost/cli/docker_cmd.py`:

```python
"""`devboost docker` — the Docker runtime on macOS (colima | orbstack | docker-desktop)."""

from __future__ import annotations

from typing import Annotated

import typer

from devboost.cli import host as plat
from devboost.core import log, osinfo
from devboost.core.errors import ConfigError, DevbootError, NeedsUser
from devboost.core.userconfig import parse_docker_runtime, selected_docker_runtime
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.modules._docker_switch import REQUIRED, switch_runtime

app = typer.Typer(
    help="Docker runtime on macOS: colima (default) | orbstack | docker-desktop",
    no_args_is_help=True,
)

_WARNING = (
    "Images, volumes and ddev databases live inside each runtime's VM — they do not "
    "move to the new runtime."
)


@app.command("use")
def use(
    runtime: Annotated[str, typer.Argument(help="colima | orbstack | docker-desktop")],
    snapshot: Annotated[
        bool | None,
        typer.Option(
            "--snapshot/--no-snapshot",
            help="run `ddev snapshot --all` first (asked when omitted)",
        ),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="never prompt (snapshots unless --no-snapshot)")
    ] = False,
) -> None:
    """Switch this Mac's Docker runtime and reconfigure what depends on it."""
    info = osinfo.detect()
    if info.family != "macos":
        raise typer.BadParameter("`devboost docker use` is macOS-only — Linux runs docker-ce")
    try:
        target = parse_docker_runtime(runtime)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    previous = selected_docker_runtime()
    ex = RealExecutor()
    ctx = Ctx(os=info, ex=ex)
    log.warn(_WARNING)
    if snapshot is None:
        snapshot = ex.which("ddev") and (
            yes or typer.confirm("Snapshot every ddev project first (ddev snapshot --all)?",
                                 default=True)
        )
    try:
        with plat.mac_session(ctx.os, dry_run=False):
            report = switch_runtime(ctx, target, snapshot=snapshot)
    except NeedsUser as exc:
        log.error(f"blocked: {exc.reason}")
        typer.echo(f"  fix: {exc.how_to_fix}")
        typer.echo(f"  or go back: devboost docker use {previous}")
        raise typer.Exit(code=1) from exc
    except DevbootError as exc:
        log.error(str(exc))
        typer.echo(f"  go back: devboost docker use {previous}")
        raise typer.Exit(code=1) from exc
    for name, ok in report.checks:
        if ok:
            typer.echo(f"  ok    {name}")
        elif name in REQUIRED:
            typer.echo(f"  FAIL  {name}")
        else:
            typer.echo(f"  --    {name}  (not set up — devboost install {name})")
    if not report.ok:
        raise typer.Exit(code=1)
    log.ok(f"docker runtime: {report.previous} → {report.target}")
```

`engine/src/devboost/cli/app.py`: add `from devboost.cli import docker_cmd as _docker_cmd` next to the other sub-app imports, and `app.add_typer(_docker_cmd.app, name="docker")` after `app.add_typer(_secrets_cmd.app, name="secrets")`.

Note: `cli/host.py`'s `LINUX_ONLY` is **not** changed. `docker` exists on every OS; only `use` refuses off macOS, and it gives the reason.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/modules/test_docker_switch.py tests/cli/ -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. If `test_use_asks_when_not_told` sees no prompt, the fixture's `FakeExecutor(present={"ddev"})` is not being used. Check that `docker_cmd.RealExecutor` is the patched name.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_docker_switch.py src/devboost/cli/docker_cmd.py \
  src/devboost/cli/app.py tests/modules/test_docker_switch.py tests/cli/test_docker_cmd.py
git commit -m "feat(cli): devboost docker use — switch the macOS Docker runtime"
```

---

### Task 13: `doctor` — selected Docker runtime healthy

**Files:**
- Modify: `engine/src/devboost/cli/doctor.py`
- Test: `engine/tests/cli/test_doctor_docker.py` (create)

**Interfaces:**
- Consumes: `selected_runtime`, `rosetta_present` (Task 4/7).
- Produces: `doctor._docker_runtime_check(ctx) -> Check`, named `docker-runtime`, appended to `run_checks` on macOS.

- [ ] **Step 1: Write the failing tests** (`tests/cli/test_doctor_docker.py`)

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli import doctor
from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
SHOW = (("context", "show"), Result(0, stdout="colima\n"))


def test_healthy_colima() -> None:
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=RuleExecutor(rules=[SHOW])))
    assert check.name == "docker-runtime" and check.ok is True
    assert "colima" in check.detail and "healthy" in check.detail


def test_not_installed_is_informational() -> None:
    ex = RuleExecutor(rules=[(("--versions", "colima"), Result(1))])
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex))
    assert check.ok is True and "devboost install docker" in check.detail


def test_installed_but_down_fails() -> None:
    ex = RuleExecutor(rules=[SHOW, (("info",), Result(1))])
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex))
    assert check.ok is False and "not reachable" in check.detail


def test_colima_without_rosetta_notes_the_slowdown() -> None:
    ex = RuleExecutor(rules=[SHOW, (("-x86_64",), Result(1))])
    assert "qemu" in doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail


def test_bad_selection_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad() -> None:
        raise ConfigError("unknown docker runtime 'podman'")

    monkeypatch.setattr(doctor, "selected_runtime", bad)
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=RuleExecutor()))
    assert check.ok is False and "podman" in check.detail


def test_only_macos_runs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))
    names = {c.name for c in doctor.run_checks(Ctx(os=FEDORA, ex=FakeExecutor()), tmp_path)}
    assert "docker-runtime" not in names
    mac_ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                          scripts={"security": Result(44)})
    mac_names = {c.name for c in doctor.run_checks(Ctx(os=MAC, ex=mac_ex), tmp_path)}
    assert "docker-runtime" in mac_names
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/cli/test_doctor_docker.py -v`
Expected: FAIL with `AttributeError: module 'devboost.cli.doctor' has no attribute '_docker_runtime_check'`.

- [ ] **Step 3: Implement** (`engine/src/devboost/cli/doctor.py`)

Imports: `from devboost.modules._docker_runtime import rosetta_present, selected_runtime`. Add:

```python
def _docker_runtime_check(ctx: Ctx) -> Check:
    """macOS: the selected Docker runtime answers on its context (spec §8)."""
    try:
        rt = selected_runtime()
    except DevbootError as exc:
        return Check("docker-runtime", False, str(exc))
    if not rt.installed(ctx):
        return Check("docker-runtime", True, f"{rt.name} not installed (devboost install docker)")
    ok = rt.verify(ctx)
    detail = (
        f"{rt.name} (context {rt.context_name}) healthy"
        if ok
        else f"{rt.name} engine not reachable on context {rt.context_name} — "
        "run: devboost install docker"
    )
    if rt.name == "colima" and not rosetta_present(ctx):
        detail += "; Rosetta absent — amd64 images run under qemu (slower)"
    return Check("docker-runtime", ok, detail)
```

In `run_checks`, inside the final `if ctx.os.family == "macos":` block, add `checks.append(_docker_runtime_check(ctx))` after the permissions check. (`DevbootError` is already imported.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/cli/ -v && uv run mypy && uv run ruff check`
Expected: PASS, clean. `test_doctor_macos.py` is unchanged and still passes: it asserts specific names, not `all_ok`.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/doctor.py tests/cli/test_doctor_docker.py
git commit -m "feat(doctor): report the selected Docker runtime's health on macOS"
```

---

### Task 14: The M4 set plans cleanly on macOS and on Fedora

**Files:**
- Test: `engine/tests/core/test_macos_m4_plan.py` (create)

**Interfaces:**
- Consumes: everything above; `profiles.toml` as modified by M3 and Task 11.

- [ ] **Step 1: Write the test**

```python
"""Every M4 module has a macOS answer and still plans on Fedora (spec §9 contract)."""

from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from tests.core.test_macos_contract import KNOWN_GAPS, resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
M4 = (
    "docker", "docker-build-gc", "ddev", "ddev-remote", "data-services", "aspire",
    "aspire-gc", "restic-backup", "restic-b2", "obsidian-sync", "browser-mcp",
)


def test_no_m4_module_is_a_known_gap() -> None:
    assert not set(M4) & KNOWN_GAPS


def test_every_m4_module_resolves_on_macos() -> None:
    modules = load()
    assert [n for n in M4 if not resolvable_on_macos(modules[n])] == []


def test_the_m4_modules_plan_on_macos(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(list(M4), modules), modules, MAC, gpu_marker=tmp_path / "x")
    # Only the M4 modules themselves: a dependency may rightly be `provided-by-macos`.
    skipped = {p.name: p.skip_reason for p in plan if p.skip_reason and p.name in M4}
    assert skipped == {}
    assert set(M4) <= {p.name for p in plan}


def test_linux_keeps_its_timers_and_drops_browser_mcp(tmp_path: Path) -> None:
    modules = load()
    linux = [n for n in M4 if n != "browser-mcp"]
    plan = build_plan(toposort(linux, modules), modules, FEDORA, gpu_marker=tmp_path / "x")
    names = {p.name for p in plan if p.skip_reason is None}
    assert set(linux) <= names
    assert "homebrew" not in names and "browser-mcp" not in names
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/core/test_macos_m4_plan.py -v`
Expected: PASS. An M4 module in `skipped` (e.g. `unsupported-os`) has no macOS path. Fix it in the M4 task that owns it. An M4 module missing from the plan means `toposort` failed on its dependencies, which is an M3 gap: record it in the PR description. If `aspire` is blocked only by an unresolved `dotnet-sdk` (A3), mark just that test `xfail(strict=True, reason="dotnet-sdk macOS is M3")`. Do not weaken the assertion.

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_macos_m4_plan.py
git commit -m "test(macos): the M4 docker/timer set plans cleanly on macOS and Fedora"
```

---

### Task 15: Docs — `docker-runtimes.md`, `macos.md`, the rest, and the spec

**Files:**
- Create: `docs/docker-runtimes.md`
- Modify: `docs/macos.md` (M2 created it), `docs/obsidian-sync.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `dotfiles/dot_config/systemd/user/README.md`, `README.md`, `CHANGELOG.md`, `docs/superpowers/specs/2026-09-18-macos-support-design.md`

Spec §10: "Each milestone PR ships its own docs; a PR is not done without them." `docs/docker-runtimes.md` is the M4 row.

- [ ] **Step 1: Create `docs/docker-runtimes.md`** with exactly this content:

````markdown
# Docker runtimes on macOS

Linux runs Docker's own engine (docker-ce). A Mac needs a Linux VM, and dev-boost supports three ways to run one. You choose once; `devboost docker use` switches later.

| | **Colima** (default) | OrbStack | Docker Desktop |
|---|---|---|---|
| Licence | MIT — free for any use | Free for personal, non-commercial use only; work use needs Pro ($8/user/month) | Free only if the organisation you work for has **fewer than 250 employees and less than US$10M revenue**; otherwise a paid subscription |
| Installed as | brew `colima`, `docker`, `docker-compose`, `docker-buildx` | cask `orbstack` | cask `docker-desktop` |
| VM size | half the CPUs (≥ 2), a quarter of the RAM (≥ 4 GiB), 100 GiB disk — set when the VM is first created | same numbers via `orb config` | same numbers in its settings file |
| Starts at login | `brew services start colima` | `orb config set app.start_at_login true` | its "Start when you sign in" setting |
| docker context | `colima` | `orbstack` | `desktop-linux` |
| `/var/run/docker.sock` | a root LaunchDaemon `dev.devboost.docker-sock` re-links it at every boot | OrbStack manages it | Docker Desktop manages it |
| Daemon config | `docker:` in `colima.yaml` | `~/.orbstack/config/docker.json` | `~/.docker/daemon.json` |

The Mac does employer and client work, so dev-boost defaults to Colima. With ddev's default Mutagen sync, its performance is close to OrbStack's. Picking OrbStack or Docker Desktop prints the licence line above as a warning.

## Choosing a runtime

Precedence: `DEVBOOST_DOCKER_RUNTIME` > `docker_runtime` in `~/.config/devboost/config.toml` > `colima`.

```toml
# ~/.config/devboost/config.toml
docker_runtime = "colima"   # colima | orbstack | docker-desktop
```

`devboost install docker` sets up the selected runtime. `docker-build-gc` caps BuildKit's cache at 20 GB in that runtime's daemon config.

## Switching: `devboost docker use <runtime>`

```sh
devboost docker use orbstack          # asks whether to snapshot ddev databases first
devboost docker use colima --yes      # no prompts; snapshots
devboost docker use colima --no-snapshot
```

1. Images, volumes and ddev databases live **inside each runtime's VM**, so they do not move. The command offers `ddev snapshot --all` first; restore a project with `ddev snapshot restore --latest` after the switch.
2. `ddev poweroff`.
3. The old runtime is stopped and its login start disabled. It is **not** uninstalled.
4. The new runtime is installed, configured and started. The docker context, the socket and the build-cache cap follow it.
5. The choice is saved, and `docker`, `docker-build-gc`, `aspire-gc`, `ddev` and `data-services` are re-verified.

If a step fails (for example OrbStack or Docker Desktop still needs its first launch), the saved choice is unchanged and the command prints how to fix it, or `devboost docker use <previous>` to go back. Running `devboost docker use <current>` again repairs the current runtime.

## One-time manual steps

- **OrbStack:** `open -a OrbStack` once and finish onboarding. Choose Pro if the Mac is used for work.
- **Docker Desktop:** `open -a Docker` once and accept the Docker Subscription Service Agreement.
- **ddev:** `mkcert -install` asks for your password, or for a keychain approval, the first time.

## Colima details

- **Config dir.** Colima looks for `$COLIMA_HOME`, then `~/.colima`, then `$XDG_CONFIG_HOME/colima` (`~/.config/colima`). On a fresh Mac dev-boost creates `~/.config/colima` first, so your shell and the login service use the same VM. An existing `~/.colima` is kept. If you set `XDG_CONFIG_HOME` to something other than `~/.config`, also set `COLIMA_HOME`.
- **Rosetta.** `--vz-rosetta` (fast amd64 containers) is used only when Rosetta 2 is installed. Without it, amd64 images run under qemu, and `devboost doctor` says so.
- **Resizing.** Edit `colima.yaml` (`colima start --edit`) or run `colima stop && colima start --cpu 6 --memory 8`. dev-boost sizes the VM only when it creates it.
- **Comments.** dev-boost edits `colima.yaml` with a YAML library, so the file's comments are dropped the first time the build-cache cap is merged in.
- **DNS.** If containers cannot resolve names, DDEV's docs suggest `colima start --dns=1.1.1.1`. dev-boost does not set this by default, because it breaks company VPNs that use split DNS.

## Scheduled jobs (launchd)

The Linux systemd `--user` timers run on macOS as LaunchAgents in `~/Library/LaunchAgents`, on the same schedule. Logs go to `~/Library/Logs/devboost/<name>.log`.

| Job (label `dev.devboost.<name>`) | Schedule | Runs |
|---|---|---|
| `aspire-gc` | hourly, at :00 | `devboost dev gc` |
| `restic-backup` | daily, 00:00 | `restic backup --files-from ~/.config/devboost/restic-include` |
| `restic-b2` | daily, 00:00 | `restic init` (once), `backup`, then `forget --prune` (7 daily / 4 weekly / 6 monthly) |
| `obsidian-sync` | daily, 00:00 | commit, pull `--rebase`, push the vault |
| `browser-mcp` | always on (restarts on failure, at most once a minute) | `~/.local/bin/browser-mcp` |

A job whose time passed while the Mac was **asleep** runs once on wake, like systemd's `Persistent=true`. A run missed while the Mac was **off** is skipped. `restic-backup` behaves as it does on Linux: it expects `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` in the job's environment. Use `restic-b2` for a configured offsite backup.

```sh
launchctl print gui/$(id -u)/dev.devboost.aspire-gc   # state, last exit code
launchctl kickstart gui/$(id -u)/dev.devboost.restic-b2   # run now
tail -f ~/Library/Logs/devboost/restic-b2.log
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | `docker context show` should name your runtime; `devboost doctor` shows `docker-runtime`; re-run `devboost docker use <current>` |
| Colima: "found ~/.colima, ignoring $XDG_CONFIG_HOME" | harmless; to silence, `mv ~/.colima ~/.config/colima` while Colima is stopped |
| `brew link` conflict on `docker` after trying Docker Desktop | `devboost docker use colima` relinks the formulae |
| Aspire containers cannot reach the dashboard | Colima resolves `host.docker.internal`; check `docker context show` and that the dashboard runs |
````

- [ ] **Step 2: `docs/macos.md`**. Add a section `## Docker, ddev, Aspire and scheduled jobs (M4)` with three short paragraphs:
  1. Colima is the default runtime; see `docker-runtimes.md` for the licensing table and `devboost docker use`.
  2. `devboost install laravel dotnet data dev-hygiene` gives ddev (`brew install ddev/ddev/ddev`, `mkcert -install`), the Aspire CLI (`dotnet tool` in `~/.dotnet`) and the data-services compose template. The postgres, valkey and dbgate images are multi-arch.
  3. The timers are LaunchAgents labelled `dev.devboost.<name>`; `browser-mcp` is an always-on agent in the `remote` profile.

  In its *dropped / provided* table, add `browser-mcp → engine module on macOS (systemd unit via dotfiles on Linux)`.

- [ ] **Step 3: The rest**
  - `docs/obsidian-sync.md`: after the systemd timer paragraph, add: "On macOS the daily push is the LaunchAgent `dev.devboost.obsidian-sync` (log: `~/Library/Logs/devboost/obsidian-sync.log`)."
  - `dotfiles/dot_config/systemd/user/README.md`: under the heading, add: "**macOS:** there is no systemd; `devboost install browser-mcp` (profile `remote`) runs the same launcher as the LaunchAgent `dev.devboost.browser-mcp`. The launcher finds Chrome at `/Applications/Google Chrome.app` (override with `CHROME_APP`)."
  - `docs/architecture.md`, *Layout → modules/*: add one bullet: "`_docker_runtime.py` + `_docker_{colima,orbstack,desktop}.py` — the macOS `DockerRuntime` protocol and its three implementations; `_launchd_jobs.py` — `LaunchdTimer`, the macOS twin of the systemd `--user` timers." In the CLI list, add `docker`.
  - `docs/adding-a-module.md`, in the macOS section M1/M2 wrote: add "**Scheduled job?** Declare `per_os = OsMap(macos=LaunchdTimer(name, script, "hourly"|"daily", formulae=(…)))` next to the systemd units, and hand off with `os_strategy` (see `modules/dev_hygiene.py`)."
  - `README.md`: in the macOS install section, add one line: "Docker on a Mac is Colima by default (free for work use); see [docs/docker-runtimes.md](docs/docker-runtimes.md) for OrbStack / Docker Desktop and `devboost docker use`." `profiles.toml` changed (`remote` += `browser-mcp`), so regenerate the README profile tables with `scripts/gen_profiles_table.py` the way M2 did (read its docstring for the invocation).
  - `CHANGELOG.md`, under *Unreleased → Added*: "macOS: Docker runtimes (Colima default, OrbStack, Docker Desktop) and `devboost docker use`; ddev, Aspire and data-services on the Mac; aspire-gc, restic-backup, restic-b2, obsidian-sync and browser-mcp as launchd agents; `doctor` reports the Docker runtime." Under *Changed*: "PyYAML is a new runtime dependency (Colima's `colima.yaml`)."

- [ ] **Step 4: Spec** (`docs/superpowers/specs/2026-09-18-macos-support-design.md`)
  - §4 table, `/var/run/docker.sock` row, Colima cell: `root LaunchDaemon dev.devboost.docker-sock (ln -sf at boot; /var/run is emptied at boot)`.
  - §4, after the sizing paragraph, add: "Colima's config dir is resolved as Colima does, and a fresh Mac pins `~/.config/colima` (plan D10). The VM is created once with `colima start <flags>` and then handed to `brew services` (D11). `colima.yaml` is merged with PyYAML (D12). Docker Desktop's `settings-store.json` keys are matched case-insensitively (D14)."
  - §2 per-OS table, row `aspire-gc, restic-backup, restic-b2, obsidian-sync, browser-mcp`: append "; `StartCalendarInterval` hourly `{Minute:0}` / daily `{Hour:0,Minute:0}`; logs `~/Library/Logs/devboost/`; browser-mcp is a macOS-only module in `remote` (KeepAlive on failure)".
  - §11 M4 row: append "(`build-gc` = `docker-build-gc`, a daemon-config cap, not a timer)".

- [ ] **Step 5: Check the links, then commit** (repo root)

```bash
grep -rn 'docker-runtimes.md' README.md docs/macos.md
git add docs/docker-runtimes.md docs/macos.md docs/obsidian-sync.md docs/architecture.md \
  docs/adding-a-module.md dotfiles/dot_config/systemd/user/README.md README.md CHANGELOG.md \
  docs/superpowers/specs/2026-09-18-macos-support-design.md
git commit -m "docs(macos): Docker runtimes, docker use, launchd jobs (M4)"
```

---

### Task 16: Final gate, acceptance on the real Mac, PR

The CI suite proves the argv and plists. This task proves the outcome, "ddev, Aspire, data-services", on this Mac (macOS 27, Apple Silicon). It uses real brew, Colima and launchd. Nothing here is automated in CI.

**Files:** none (unless a step finds a bug; fix it test-first in the task that owns the code)

- [ ] **Step 1: Full gate** (from `engine/`)

```bash
uv run ruff check && uv run mypy && uv run pytest 2>&1 | tail -3
grep -cE '^    "' tests/core/test_macos_contract.py
```
Expected: all green. The `KNOWN_GAPS` count is lower than Task 0's by the number of names Tasks 7–10 removed.

- [ ] **Step 2: Install the M4 set from the clone** (repo root; the devboost under test is the working tree)

```bash
cd engine && uv run devboost install docker docker-build-gc ddev aspire data-services aspire-gc browser-mcp
```
Expected: every module `ok`, except `ddev`, which may be `blocked` with the `mkcert -install` fix. Run that once and re-run the install. Then:

```bash
docker context show                                   # colima
docker info --format '{{.OperatingSystem}} {{.Architecture}}'
ls -l /var/run/docker.sock                            # → ~/.config/colima/default/docker.sock
brew services info colima --json | grep '"running": true'
grep -A4 '^docker:' ~/.config/colima/default/colima.yaml   # builder.gc present
launchctl print gui/$(id -u)/dev.devboost.aspire-gc | grep -E 'state|path'
uv run devboost doctor | grep docker-runtime          # ok … healthy
```

- [ ] **Step 3: The outcome: ddev, Aspire, data-services**

```bash
COMPOSE="$(git rev-parse --show-toplevel)/templates/data/compose.yaml"   # run from the repo
mkdir -p ~/repos/m4-laravel && cd ~/repos/m4-laravel      # Colima mounts only $HOME
ddev config --project-type=laravel --docroot=public && ddev start && ddev describe
ddev poweroff
mkdir -p ~/repos/m4-aspire && cd ~/repos/m4-aspire
~/.dotnet/tools/aspire new aspire-starter --name M4 --output . --non-interactive
gtimeout 120 ~/.dotnet/tools/aspire run || true   # dashboard URL printed; containers start
docker compose -f "$COMPOSE" up -d
docker compose -f "$COMPOSE" ps                   # postgres, valkey, dbgate running
docker compose -f "$COMPOSE" down
rm -rf ~/repos/m4-laravel ~/repos/m4-aspire
```
Expected: the ddev project answers on its `https://*.ddev.site` URL with a trusted certificate. `aspire run` starts its containers on Colima. The three data services come up as arm64 images. If `aspire new`'s template flags differ in the installed CLI, use `aspire new --help`; the point is `aspire run` against Colima.

- [ ] **Step 4: Timers fire**

```bash
launchctl kickstart -p gui/$(id -u)/dev.devboost.aspire-gc
sleep 5; tail -5 ~/Library/Logs/devboost/aspire-gc.log    # "gc: removed N orphaned container(s)"
```

- [ ] **Step 5: Switch round trip** (only if you accept OrbStack's or Docker Desktop's terms for this test; otherwise record "switch verified by unit tests only" in the PR)

```bash
uv run devboost docker use orbstack --no-snapshot     # first time: blocked → open -a OrbStack, repeat
docker context show                                   # orbstack
brew services info colima --json | grep '"running": false'
uv run devboost docker use colima --no-snapshot
docker context show && ls -l /var/run/docker.sock     # colima again
```

- [ ] **Step 6: Reboot check (D13)**. Reboot the Mac, log in, wait a minute, then:

```bash
ls -l /var/run/docker.sock && docker info >/dev/null && echo OK
```
Expected: `OK`. The link was re-created by `dev.devboost.docker-sock` and Colima was started by `brew services`. If the link is missing, check `sudo launchctl print system/dev.devboost.docker-sock` before changing any code.

- [ ] **Step 7: Linux regression**. From the repo root, run the Fedora and Ubuntu VM smoke tests the way M2 did (`scripts/vm-test.sh`, see `docs/vm-testing.md`), installing `docker docker-build-gc aspire-gc`. Expected: unchanged behaviour: docker-ce, `/etc/docker/daemon.json`, `~/.config/systemd/user/aspire-gc.timer`.

- [ ] **Step 8: PR** (repo root)

```bash
git push -u origin feat/macos-m4-docker
gh pr create --title "feat(macos): M4 — Docker runtimes, docker use, launchd timers" --body-file - <<'MD'
## Summary
- Colima (default, MIT) / OrbStack / Docker Desktop behind a `DockerRuntime` protocol; `devboost docker use`
- ddev, Aspire and data-services on macOS; `docker-build-gc` caps the selected runtime's daemon config
- aspire-gc, restic-backup, restic-b2, obsidian-sync, browser-mcp as launchd agents (`dev.devboost.<name>`), same schedules
- `doctor` checks the runtime; `docs/docker-runtimes.md` (licensing, switching, jobs)

## Decisions
See the plan's Decisions D1–D22 (docs/superpowers/plans/2026-09-19-macos-m4-docker-timers.md).

## Acceptance on macOS 27
<paste Steps 2–6 results; note any M3 gaps found by Task 14>

## Test plan
- [ ] ruff, mypy --strict, pytest green
- [ ] Fedora + Ubuntu vm-test unchanged
MD
```

The PR body carries no AI attribution (constitution).

---

## Self-review (done while writing this plan)

- **Spec coverage.** §4 protocol (`install`, `configure`, `start`, `stop`, `disable_autostart`, `verify`, `daemon_config_path`, `context_name`, plus `release_socket`, merge/has/restart for the daemon config): Tasks 4–6. §4 table, all rows × three runtimes: Tasks 5–6. Sizing: Task 4. Selection precedence and `Settings.docker_runtime`: Task 3. `docker use` steps 1–5: Task 12. Verify on context: Task 4 `engine_verified`. Multi-arch data-services: Task 8. §0 Rosetta gate: Tasks 4–5, 13. §2 per-OS rows for docker, docker-build-gc, ddev (+ mkcert), aspire-gc, restic-backup, restic-b2, obsidian-sync, browser-mcp, and restic via PATH: Tasks 7–11. §1 `NeedsUser` for OrbStack/Docker Desktop first launch and mkcert: Tasks 6, 8. §8 doctor runtime health: Task 13. §9 `DockerRuntime` argv, switch path incl. snapshot prompt, selection precedence, launchd plist equality: Tasks 1, 3–7, 9–12. §10 `docs/docker-runtimes.md` incl. licensing: Task 15. §11 M4 outcome: Task 16.
- **Placeholder scan.** No TBD/TODO. Two deliberate "existing body unchanged" markers (`...` in Task 7 Step 3) point at code already in the file; they are not code to write.
- **Type consistency.** `DockerRuntimeName` (Task 3) is used everywhere. `runtime_for`/`selected_runtime` are defined in Task 7 and used in Tasks 12–13. `schedule_job`/`job_scheduled`/`LaunchdTimer` are defined in Task 9 and used in Tasks 10–11. `BUILDER_GC` is renamed in Task 7 and imported in Task 12. `launchd.agent_installed` is defined in Task 1 and used in Tasks 9 and 11.

## Sources

- OrbStack pricing/licensing: <https://docs.orbstack.dev/faq> ("Personal use: free … Business and commercial use: $8/user/mo"); Docker context, `docker.json`, `orb start/stop/restart docker`: <https://docs.orbstack.dev/docker/>; `orb config` keys: <https://docs.orbstack.dev/settings>, <https://docs.orbstack.dev/headless>; `app.start_at_login`: <https://github.com/orbstack/orbstack/issues/1581>
- Docker Desktop terms: <https://www.docker.com/pricing/faq/> ("fewer than 250 employees and less than US $10,000,000 … in annual revenue"); settings file location and `~/.docker/daemon.json`: <https://docs.docker.com/desktop/settings-and-maintenance/settings/>; `docker desktop start|stop|restart|status`: <https://docs.docker.com/desktop/features/desktop-cli/>; settings keys undocumented: <https://github.com/docker/docs/issues/23706>; cask artifacts (`docker`, `docker-compose` binaries): <https://formulae.brew.sh/api/cask/docker-desktop.json>
- Colima (MIT, v0.10.3): <https://github.com/abiosoft/colima>; formula `service` block (`colima start -f`, `keep_alive successful_exit: true`): <https://github.com/Homebrew/homebrew-core/blob/main/Formula/c/colima.rb>; config-dir resolution (`config/files.go`), `docker:` daemon config, socket path, `host.docker.internal` mapping, immutable `vmType` (Context7 `/abiosoft/colima`)
- DDEV on macOS: <https://docs.ddev.com/en/stable/users/install/docker-installation/> (Colima command incl. `--dns=1.1.1.1`, OrbStack/Colima/Docker Desktop support); <https://docs.ddev.com/en/stable/users/install/ddev-installation/> (`brew install ddev/ddev/ddev`, `mkcert -install`)
- Aspire: prerequisites (OCI runtime; Docker CLI), `dotnet tool install -g Aspire.Cli`, `ASPIRE_CONTAINER_RUNTIME` (Context7 `/microsoft/aspire.dev`)
