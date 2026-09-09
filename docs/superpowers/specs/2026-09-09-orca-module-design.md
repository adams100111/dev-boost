# Orca module — design

**Date:** 2026-09-09
**Status:** Design approved. Fact-checked via the repo/docs + `docs/reference/headless-linux-server.md`
+ release API + AUR RPC. **Builds on the now-landed Omarchy/Arch support** (PR #27: `Pacman`
backend with `install_aur`, `ID_LIKE`-based Omarchy detection).
**Mission fit:** Opt-in module family to install and run **Orca** (stablyai/orca) across the fleet —
Fedora + Omarchy laptops (desktop) and Ubuntu/Fedora headless boxes (server) — with per-OS/arch
seams and latest-tracking updates.

## What Orca is (verified)

Orca (`stablyai/orca`, MIT, Stably AI) is an Electron "Agent Development Environment": it orchestrates
multiple AI coding agents in parallel git worktrees. **One artifact = three roles** — desktop GUI,
the bundled CLI, and headless `serve`. `git` is the only hard prereq (agent CLIs/keys are BYO). No
Docker image, no `curl|sh`; direct release-asset install (Fedora `.rpm`, Ubuntu `.deb`, AppImage) or
the AUR on Arch. **The Linux command is `orca-ide`** (renamed to avoid GNOME Orca) from the `.rpm`/
`.deb`; the **AUR `stably-orca-bin` package installs it as `stably-orca`** (a wrapper over an
extracted AppImage in `/opt`). Headless `orca-ide serve` needs Xvfb (Orca auto-starts its own on
`:99` if Xvfb is installed and `DISPLAY` unset) + `LIBGL_ALWAYS_SOFTWARE=1`; **never auto-updates
headless**; state in the run user's `~/.config/orca` + `~/.config/Orca`.

## Decisions

1. **Install spine = native everywhere.** Fedora → download latest `orca-ide-<ver>.<arch>.rpm` +
   `dnf install`; Ubuntu → latest `orca-ide_<ver>_<arch>.deb` + `apt install`; **Omarchy/Arch →
   `pkg.install_aur(ctx, "stably-orca-bin")`** (upstream-recommended; matches the existing
   `ddev-bin`/`visual-studio-code-bin` pattern; no AppImage/FUSE plumbing). The Fedora/Ubuntu
   release-asset download uses a per-OS `sh -c` (curl the releases API → match the OS+arch asset →
   download → local install), the codebase's release-fetch idiom (`code_server`, `pi-harness`).
2. **Command name is per-OS.** `_ORCA_CMD = OsMap(fedora="orca-ide", debian="orca-ide",
   arch="stably-orca")`. `verify` = `which(_ORCA_CMD.get(os))`.
3. **Version:** Fedora/Ubuntu track the latest release, pinnable via `DEVBOOST_ORCA_VERSION`; Arch
   tracks whatever `stably-orca-bin` currently ships (AUR-maintained, rolling — not dev-boost-pinned).
4. **Headless server runs as the `dev` user via systemd `--user` + linger** (non-root; linger keeps
   `serve` up across logout). **Fedora + Debian only** (the headless-server distros; Arch is
   desktop-only here — no `orca-serve` on Arch).
5. **Pairing address:** `DEVBOOST_ORCA_PAIRING_ADDRESS` → else `tailscale ip -4` → else `ConfigError`.
   Port `DEVBOOST_ORCA_PORT` (default `6768`).
6. **Two opt-in profiles, neither in `full`:** `orca = [orca-ide]` (laptops) and
   `orca-box = [orca-ide, orca-serve]` (headless). Module names `orca-ide`/`orca-serve` are disjoint
   from profile names `orca`/`orca-box`.

## Architecture

| Module | Job | `requires` | profiles | families |
|---|---|---|---|---|
| `orca-ide` | Install Orca latest per-OS: Fedora `.rpm`→dnf, Ubuntu `.deb`→apt, Arch `install_aur("stably-orca-bin")`. `verify` = `which(_ORCA_CMD.get(os))`. | — | `orca` | fedora, debian, arch |
| `orca-serve` | Headless box: ensure Xvfb; write `~/.config/systemd/user/orca-serve.service` running `orca-ide serve --port <p> --pairing-address <addr>` (`LIBGL_ALWAYS_SOFTWARE=1`, `Restart=on-failure`, `RestartPreventExitStatus=3`); `loginctl enable-linger <user>`; enable+start. | `OrcaIde` | `orca-box` | fedora, debian |

`families` (the omarchy branch's per-module OS-scoping) restricts each module to the OSes it supports,
so `build_plan` drops it cleanly elsewhere. `orca-ide` = {fedora, debian, arch}; `orca-serve` =
{fedora, debian}.

### `orca-ide` install

- **fedora / debian:** per-OS `sh -c`: resolve the newest asset from
  `api.github.com/repos/stablyai/orca/releases/{latest|tags/v<VER>}` matching
  `orca-ide-.*\.<x86_64|aarch64>\.rpm` / `orca-ide_.*_<amd64|arm64>\.deb`, `curl` it to a temp file,
  `sudo dnf install -y` / `sudo apt install -y` (resolves the Electron deps). Raise `ConfigError`/
  `InstallError` on failure.
- **arch:** `pkg.install_aur(ctx, "stably-orca-bin")` (AUR helper / `omarchy-pkg-aur-add` / yay / paru).
- **verify / update:** `which(_ORCA_CMD.get(os))`; on `--force`, reinstall latest (dnf/apt reinstall;
  AUR re-install). Idempotent. NOTE: do **not** set `gui=True` on `orca-ide` — `build_plan` skips
  `gui=True` modules on headless hosts, which would break `orca-serve`'s dependency on a server.
- **update path:** dev-boost re-fetch on `--force` (packaged installs are root-owned, so Orca's
  Electron self-updater can't rewrite them; updates come through the package/re-fetch, not auto-update).

### `orca-serve`

- Ensure Xvfb via `pkg.install(ctx, OsMap(fedora="xorg-x11-server-Xvfb", debian="xvfb"))` (the
  Electron libs come from the `orca-ide` package deps).
- Resolve pairing address (env → `tailscale ip -4` → `ConfigError`) and port.
- `systemd.write_user_unit(ctx, "orca-serve.service", <unit>)` with
  `ExecStart=/usr/bin/xvfb-run -a orca-ide serve --port <PORT> --pairing-address <ADDR>`,
  `Environment=LIBGL_ALWAYS_SOFTWARE=1`, `Restart=on-failure`, `RestartPreventExitStatus=3`. The
  `xvfb-run -a` wrapper is belt-and-suspenders: the packaged `orca-ide serve` auto-starting its own
  Xvfb is *implied* (app-build behavior) but never doc-demonstrated for the package, so we allocate a
  display deterministically. Non-root ⇒ no `--no-sandbox`.
- `ctx.ex.run(["loginctl","enable-linger",<user>], sudo=True)`; `systemd.enable_user_unit(ctx,
  "orca-serve.service", now=True)`.
- **verify:** `systemd.is_enabled(ctx, "orca-serve.service", user=True)`.
- **update:** manual by design (headless never self-updates) — the module logs that re-running
  `orca-ide` (with `--force`) + `systemctl --user restart orca-serve` upgrades the box.

## Cross-cutting

- **Omarchy detection is already in main** (`ID_LIKE`) — no osinfo change needed.
- **Reuses the landed `Pacman.install_aur`** — no new package-manager code.
- **GNOME Orca:** no conflict (different package/binary).
- **Optional (deferred):** a `doctor` `orca` informational check.

## Not in scope

macOS/Windows (outside Linux target); the mobile app / cloud relay / per-workspace `orca.yaml` env
targets; a dedicated non-root `orca` system user (systemd `--user` under `dev` is the model);
`orca-serve` on Arch.

## Grill addendum (verified 2026-09-09)

- **Engine runs as the invoking user** (get.sh installs to `$HOME`, runs `devboost install`
  un-elevated; modules elevate per-op). So `systemd --user` + `loginctl enable-linger <user>` is safe
  and correct (mirrors the working `aspire-gc` `--user` pattern). Username via
  `_invoking_user()` = `SUDO_USER or USER` (as `code_server`/`docker` do); linger via
  `ctx.ex.run(["loginctl","enable-linger",user], sudo=True)`.
- **Xvfb is never a package dependency** (any distro) — install it explicitly. Wrap `serve` in
  `xvfb-run -a` for a deterministic display.
- **AUR:** `stably-orca-bin` (upstream-recommended) installs the command **`stably-orca`** only —
  `_ORCA_CMD` map is correct. `stably-orca serve …` is a pass-through to the same release binary.
  Rejected `orca-ide-bin` (uniform name but unofficial maintainer) for trust.
- **`.rpm`/`.deb` GUI-runtime libs** are expected as package `Requires`/`Depends` but not
  doc-published — verify on the target rather than trusting blindly (non-blocking; dnf/apt would fail
  loudly if a dep is missing).
- **`orca-serve` needs Tailscale *up*** at install (not just installed) to derive the pairing IP:
  `DEVBOOST_ORCA_PAIRING_ADDRESS` → `tailscale ip -4` → `ConfigError`. Tailnet reachability means no
  public firewall hole for the port.
- **GitHub API** for asset resolution is unauthenticated (public repo; 60/hr is ample for installs);
  the `.rpm`/`.deb` asset download itself needs no auth.

## Sources

`github.com/stablyai/orca` (README, releases API, `docs/reference/headless-linux-server.md`);
`onorca.dev/docs/{install,remote-servers,ways-to-run,cli/overview}`; AUR `stably-orca-bin` PKGBUILD;
dev-boost `modules/{ddev,editors,code_server,apps}.py`, `exec/primitives/{pkg,systemd}.py`,
`core/osinfo.py`, `profiles.toml` (all post-omarchy `main`).
