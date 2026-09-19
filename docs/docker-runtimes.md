# Docker runtimes on macOS

Linux runs Docker's own engine (docker-ce). A Mac needs a Linux VM, and dev-boost supports three ways to run one. You choose once; `devboost docker use` switches later.

| | **Colima** (default) | OrbStack | Docker Desktop |
|---|---|---|---|
| Licence | MIT — free for any use | Free for personal, non-commercial use only; work use needs Pro ($8/user/month) | Free only for companies with **fewer than 250 employees and less than US$10M annual revenue**; otherwise a paid subscription (checked against [orbstack.dev/pricing](https://orbstack.dev/pricing) and [docker.com/pricing/faq](https://www.docker.com/pricing/faq/), 2026-09-19) |
| Installed as | brew `colima`, `docker`, `docker-compose`, `docker-buildx` | cask `orbstack` | cask `docker-desktop` |
| VM size | half the CPUs (≥ 2), a quarter of the RAM (≥ 4 GiB), 100 GiB disk — set when the VM is first created | same numbers via `orb config` | same numbers in its settings file |
| Starts at login | `brew services start colima` | `orb config set app.start_at_login true` | its "Start when you sign in" setting |
| docker context | `colima` | `orbstack` | `desktop-linux` |
| `/var/run/docker.sock` | a root LaunchDaemon `dev.devboost.docker-sock` re-links it at every boot (`/bin/ln -shf`; `/var/run` is emptied at boot) | OrbStack manages it | Docker Desktop manages it |
| Daemon config | `docker:` in `colima.yaml` | `~/.orbstack/config/docker.json` | `~/.docker/daemon.json` |

The Mac does employer and client work, so dev-boost defaults to Colima. With ddev's default Mutagen sync, its performance is close to OrbStack's. Picking OrbStack or Docker Desktop prints the licence line above as a warning.

## Choosing a runtime

Precedence: `DEVBOOST_DOCKER_RUNTIME` > `docker_runtime` in `~/.config/devboost/config.toml` > `colima`.

```toml
# ~/.config/devboost/config.toml
docker_runtime = "colima"   # colima | orbstack | docker-desktop
```

`devboost install docker` sets up the selected runtime. `docker-build-gc` caps BuildKit's cache at 20 GB in that runtime's daemon config, merging in alongside anything else already there (e.g. the `runtimes` block `nvidia-ctk` would add on an NVIDIA host, not relevant on a Mac, or your own `builder.gc.policy` / `builder.entitlements`).

`~/.config/devboost/config.toml` is rewritten wholesale (via `tomli-w`) whenever `devboost docker use` saves a new choice, so hand-added comments in that file do not survive a switch.

## Switching: `devboost docker use <runtime>`

```sh
devboost docker use orbstack          # asks whether to snapshot ddev databases first
devboost docker use colima --yes      # no prompts; snapshots
devboost docker use colima --no-snapshot
```

1. Images, volumes and ddev databases live **inside each runtime's VM**, so they do not move. The command offers `ddev snapshot --all` first; restore a project with `ddev start` then `ddev snapshot restore --latest` after the switch.
2. `ddev poweroff`.
3. **Every other installed runtime is stopped** (not only the one you're switching from — a half-finished earlier switch can leave more than one running) and its login start disabled. None of them is uninstalled: their VMs, images and volumes stay on disk.
4. The new runtime is installed, configured and started. The docker context, the socket and the build-cache cap follow it. A runtime already installed by hand (outside dev-boost, e.g. downloaded from orbstack.dev) is left as-is and just adopted.
5. The choice is saved, and `docker`, `docker-build-gc`, `aspire-gc`, `ddev` and `data-services` are re-verified.

If a step fails (for example OrbStack or Docker Desktop still needs its first launch), the saved choice is unchanged and the command prints how to fix it, or `devboost docker use <previous>` to go back — which also stops whatever a failed switch left half-started. Running `devboost docker use <current>` again repairs the current runtime. `DEVBOOST_DOCKER_RUNTIME` beats the saved choice everywhere else in dev-boost, so a conflicting env var is refused up front ("nothing was changed") rather than switching a runtime later commands won't drive.

## One-time manual steps

- **OrbStack:** `open -a OrbStack` once and finish onboarding. Choose Pro if the Mac is used for work.
- **Docker Desktop:** `open -a Docker` once and accept the Docker Subscription Service Agreement.
- **ddev:** `mkcert -install` asks for your password, or for a keychain approval, the first time. Before installing ddev itself, dev-boost runs `brew trust --tap ddev/ddev` once (Homebrew 7 refuses to install from an untrusted third-party tap otherwise) — harmless to see repeated.

## Colima details

- **Config dir.** Colima looks for `$COLIMA_HOME`, then `~/.colima`, then `$XDG_CONFIG_HOME/colima` (`~/.config/colima`) — and the same VM must be found by both your interactive shell (which has `XDG_CONFIG_HOME` set) and by `brew services`' login job (which launchd starts with neither `XDG_CONFIG_HOME` nor `COLIMA_HOME`). dev-boost pins one home both sides agree on: with the default `XDG_CONFIG_HOME` (or none set), that's `~/.config/colima`; with a custom `XDG_CONFIG_HOME`, or a `COLIMA_HOME` that doesn't exist yet, it's `~/.colima` (Colima's own first pick either way). An existing `~/.colima` is always kept as-is. If your shell and `brew services` would still disagree — an existing VM under a custom `XDG_CONFIG_HOME`, or a `COLIMA_HOME` pointed elsewhere — `docker`/`docker-build-gc` report `blocked` with the exact `colima stop; mv …` to reconcile them.
- **`~/.ssh/config`.** Colima 0.10.3 appends an `Include` line for its Lima guest's SSH config the first time a VM starts. That's Colima's own behaviour; dev-boost leaves it alone.
- **Rosetta.** `--vz-rosetta` (fast amd64 containers) is used only when this macOS still supports full Rosetta (`ROSETTA_LAST_FULL_MAJOR`) AND Rosetta 2 is installed. Without it, amd64 images run under qemu, and `devboost doctor` says so.
- **Resizing.** Edit `colima.yaml` (`colima start --edit`) or run `colima stop && colima start --cpu 6 --memory 8`. dev-boost sizes the VM only when it creates it.
- **Comments.** dev-boost edits `colima.yaml` with a YAML library (PyYAML), so the file's comments are dropped the first time the build-cache cap is merged in.
- **DNS.** If containers cannot resolve names, DDEV's docs suggest `colima start --dns=1.1.1.1`. dev-boost does not set this by default, because it breaks company VPNs that use split DNS.

## Docker Desktop details

`update_settings` matches a key devboost sets against the file's own existing spelling, case-insensitively — Docker does not publish a schema for `settings-store.json` (docker/docs#23706), so this is the safest way to update a key without guessing its exact case and creating a duplicate. Writes are atomic (a temp file in the same directory, then `os.replace`), so a crash or a lock held mid-write never leaves a truncated settings file that a later run would treat as empty and overwrite wholesale.

## Upgrading

`devboost install --update` does **not** upgrade any of the three runtimes: on macOS it only re-runs modules whose whole install is a bare `BrewFormula`/`BrewCask`, and `docker`'s macOS strategy (`_MacDocker`) is a custom `Installer` for all three runtimes, not one of those. Upgrade by hand instead:

- **Colima** (a Homebrew *formula*, not a cask — it never self-updates): `brew upgrade colima docker docker-compose docker-buildx`.
- **OrbStack** (a cask with `auto_updates` set — checked 2026-09-19): it updates itself in the app, or force it from the CLI with `brew upgrade --cask --greedy-auto-updates orbstack` (a plain `brew upgrade --cask` skips any `auto_updates` cask by design).
- **Docker Desktop** (also `auto_updates`): same as OrbStack — its own updater, or `brew upgrade --cask --greedy-auto-updates docker-desktop`.

## Scheduled jobs (launchd)

The Linux systemd `--user` timers run on macOS as LaunchAgents in `~/Library/LaunchAgents`, on the same schedule. Logs go to `~/Library/Logs/devboost/<name>.log`.

| Job (label `dev.devboost.<name>`) | Schedule | Runs |
|---|---|---|
| `aspire-gc` | hourly, at :00 | `devboost dev gc` |
| `restic-backup` | daily, 00:00 | `restic backup --files-from ~/.config/devboost/restic-include` |
| `restic-b2` | daily, 00:00 | `restic init` (once), `backup`, then `forget --prune` (7 daily / 4 weekly / 6 monthly) |
| `obsidian-sync` | daily, 00:00 | commit, pull `--rebase`, push the vault |
| `browser-mcp` | always on (restarts on failure, at most once a minute) | `~/.local/bin/browser-mcp` |

A job whose time passed while the Mac was **asleep** runs once on wake, like systemd's `Persistent=true`. A run missed while the Mac was **off** is skipped — the one difference from the systemd `--user` timers.

`restic-backup` needs `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` configured (e.g. `RESTIC_PASSWORD_FILE` in `~/.config/restic`) before its nightly run succeeds; until then it fails silently in the background like it does on Linux. `restic-b2` is the configured offsite alternative — its env file is provisioned by `devboost install restic-b2` itself. That env file is `sh`-sourced (`set -a; . <file>; set +a`) by the launchd job, so if you edit it by hand, keep it `sh`-sourceable (values `shlex.quote`d, one `KEY=value` per line) — the same as on Linux.

```sh
launchctl print gui/$(id -u)/dev.devboost.aspire-gc   # state, last exit code
launchctl kickstart gui/$(id -u)/dev.devboost.restic-b2   # run now
tail -f ~/Library/Logs/devboost/restic-b2.log
```

### browser-mcp

`browser-mcp` (profile `remote`) is the macOS twin of the Linux `browser-mcp.service` systemd unit (see `dotfiles/dot_config/systemd/user/README.md`): an always-on Playwright MCP server bound to the Tailscale interface, so a remote Claude Code session gets its own visible browser on this Mac. It is unauthenticated by design (reachable from the tailnet, not the open internet), so restrict it further with a **Tailscale ACL** scoped to `tcp:8931` on this device rather than relying on the tailnet's default allow — see the [Tailscale ACL docs](https://tailscale.com/kb/1018/acls). Never `tailscale funnel` it. The server includes `browser_run_code_unsafe`, which is RCE-equivalent, and in the pinned `@playwright/mcp@0.0.82` no flag turns it off. See [remote-dev.md](remote-dev.md#security-port-8931-runs-code-on-your-machine) for the exposure and an example ACL.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | `docker context show` should name your runtime; `devboost doctor` shows `docker-runtime`; re-run `devboost docker use <current>` |
| Colima: "found ~/.colima, ignoring $XDG_CONFIG_HOME" | harmless; to silence, `mv ~/.colima ~/.config/colima` while Colima is stopped |
| `brew link` conflict on `docker` after trying Docker Desktop | `devboost docker use colima` relinks the formulae |
| Aspire containers cannot reach the dashboard | Colima resolves `host.docker.internal`; check `docker context show` and that the dashboard runs |
| SQL Server (or any amd64-only image, e.g. Aspire's `AddSqlServer`) is slow, or won't start | SQL Server ships no arm64 image and Azure SQL Edge was retired 2025-09-30. On Colima without Rosetta, amd64 images run under qemu — install Rosetta (`devboost install rosetta`) **before** the first Colima VM is created, so `--vz-rosetta` is set; a VM created without it must be recreated. `data-services` itself stays Postgres/Valkey/dbgate (all multi-arch), so this only affects your own amd64-only images. |
| A .NET 10 container exits with 132 (SIGILL) on an Apple M4/M5 chip | Virtualization.framework guests on M4/M5 can see SME, and some .NET 10 builds crash on it. No environment-variable workaround is confirmed (`DOTNET_EnableArm64Sve=0` and `GLIBC_TUNABLES=glibc.cpu.name=generic` were both tried in dotnet/runtime#133030 and did not help — the probe is in the native runtime, not JIT-gated); update the .NET 10 image/SDK to the latest patch. See dotnet/runtime#122608, dotnet/runtime#133030, orbstack/orbstack#2670. `devboost doctor`'s `docker-runtime` check prints the same hint on an M4/M5 Mac. |
