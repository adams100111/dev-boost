# macOS M3 + Zed Z2 — Catalog on macOS, Zed on macOS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `devboost install macos` on an Apple Silicon Mac (macOS 27/26) installs the whole workstation catalog through Homebrew and per-OS strategies (Command Line Tools, Homebrew and Rosetta as modules, casks for the GUI apps, herdr pinned per OS and arch, .NET, Android SDK, ddev, Tailscale, the agent CLIs), and Zed becomes the default editor on macOS too (cask, seeded config, code/text files open in Zed). What is left without a macOS path is only the Docker runtime and the launchd timers (M4) and `pass` (P2), and those modules stop with a clear `blocked` message instead of running Linux commands.

**Architecture:** Built on M2's seams: `BrewFormula` / `BrewCask` strategies (`modules/_brew.py`), `Module.os_strategy()` with the `if (s := self.os_strategy(ctx)) is not None:` hand-off, the `plan._supported` fallback, and the `PackageModule.install_linux` / `verify_linux` hooks. M3 adds: a `modules/macos.py` foundation (`xcode-clt`, `homebrew`, `rosetta`) that every brew-backed module `requires`; a `MacosPending` strategy that marks an M4-owned module as a known gap which reports `blocked`; cask upgrades on `--update` that leave self-updating apps alone; `(os, arch)`-keyed pinned assets; a shared `exec/userpaths.py`; custom macOS strategies for `dotnet-sdk`, `android-sdk`, `ddev`, `tailscale`; and a families / provided-by / portable sweep. Z2 adds a `default_apps` primitive (on `utiluti`) that M5's `default-apps` module reuses, and routes `Zed.install` through `per_os.macos = BrewCask("zed")`.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic v2, pytest, mypy `--strict`, ruff (line ≤ 100), `uv`; Homebrew 7; POSIX sh / bash / zsh; chezmoi 2.72; TOML.

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md` (§0, §1, §2, §6, §9, §10, §11 row M3) and `docs/superpowers/specs/2026-09-18-zed-default-editor-design.md` (row Z2). Read both, and the M2 plan `docs/superpowers/plans/2026-09-19-macos-m2-shell-dotfiles.md` (the seams this plan builds on), before starting. Binding carry-over list: `.superpowers/carryover/carryover.md` (sections M3 and Z2). Format exemplar: `docs/superpowers/plans/2026-09-19-macos-m1-engine-core.md`.

## Global Constraints

- Apple Silicon only; the macOS family id is `"macos"`; Homebrew prefix `/opt/homebrew`. Supported: macOS 27 Golden Gate (primary, this Mac), 26 Tahoe; 15 best-effort.
- Brew is **never** run with `sudo`. Every brew call goes through `devboost.exec.primitives.pkg` (`install`, `installed`, `upgrade`, `install_cask`, `cask_installed`, and the new `upgrade_cask`, `cask_auto_updates`). Casks install with `--adopt`; a hand-installed app brew cannot adopt is `present-unmanaged`.
- Every module whose macOS install uses Homebrew **requires `Homebrew`** (spec §1 "Ordering"). `Homebrew` requires `XcodeClt`. Both are `families = ("macos",)`, so Linux plans drop them.
- A module that can only be finished by a person raises `NeedsUser(reason, how_to_fix)` (reported `blocked`, never `fail`). Nothing waits on a prompt nobody can see: a step that pops a macOS dialog runs only when `_credentials.is_interactive()` is true.
- Every default is free for commercial use (checked 2026-09-19, Homebrew 7.0.4 on macOS 27.0): Homebrew BSD-2-Clause; utiluti Apache-2.0; glow MIT; herdr Apache-2.0; mkcert BSD-3-Clause; ddev Apache-2.0; uv Apache-2.0/MIT; cmake BSD-3-Clause; neovim Apache-2.0; mosh GPL-3.0 (tool); smartmontools GPL-2.0 (tool); ffmpeg GPL (tool); .NET SDK and `dotnet-install.sh` MIT; Temurin GPL-2.0 + Classpath Exception; Android SDK command-line tools (Android SDK License, free); Zed GPL-3.0 (app); Obsidian (commercial licence optional since 2025-02-20); Bruno MIT; Bitwarden GPL-3.0; LocalSend Apache-2.0; VLC GPL-2.0; Tailscale client BSD-3-Clause; opt-in only: VS Code (Microsoft licence), JetBrains Toolbox (free app). Rosetta 2 and the Command Line Tools are Apple OS components.
- Every Homebrew name in this plan was checked with `brew info --json=v2` on 2026-09-19 and has an `arm64` bottle / Apple Silicon artifact: formulae `utiluti`, `glow`, `mkcert`, `uv`, `mosh`, `neovim`, `smartmontools`, `cmake`, `ffmpeg`; tap formula `ddev/ddev/ddev` (via `brew tap ddev/ddev`); casks `zed`, `obsidian`, `bruno`, `bitwarden`, `localsend`, `vlc`, `visual-studio-code`, `jetbrains-toolbox`, `tailscale-app`, `android-commandlinetools`.
- Linux behaviour does not change beyond what the specs ask for: `glow` and `herdr-plugins` join `cli` on every OS; herdr moves to the 0.9.1 pin; `chezmoi-repo` uses `--force` and reports a missing repo as `blocked`; the macOS-only modules never appear in a Linux plan. Every existing Linux test keeps its intent.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy`, `uv run pytest`, all clean. Tests are hermetic: `tests/conftest.py` autouse fixtures `_tmp_home` (HOME/XDG in `tmp_path`) and `_linux_host` (argument-less `detect()` is Fedora). Tests inject `OsInfo`; they never read the host. A test that needs an external binary skips when it is absent.
- Commit messages: Conventional Commits, **no `Co-Authored-By` trailer, no Claude/Anthropic attribution** (constitution).
- All commands run from `engine/` unless a step says otherwise. Repo-relative paths in `git add` are written from `engine/` (`../profiles.toml`, `../dotfiles/...`).

## Decisions

The specs are silent on these points, or a 2026 fact changed them. Task 16 carries each one into the specs.

| # | Decision | Why |
|---|---|---|
| D1 | **End state of `KNOWN_GAPS`:** `docker`, `docker-build-gc`, `aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync` → **M4** (Docker runtimes + launchd timers, spec §2 per-OS table and §11 M4); `pass` → **P2** (parallel). `KNOWN_GAPS` becomes a `dict[str, str]` of module → owning milestone. M5's modules (`macos-defaults`, `default-apps`, the desktop casks, `voxtype`, `xcode`, `ios-tooling`, `android-emulator`, `macos-extras`) do not exist yet, so they are not gaps; M5 creates them with their macOS path. | The task target: only M4/M5-owned gaps remain. `data-services`, `ddev` and `laravel-lsp` get their macOS answer here but stay `blocked` at run time until M4 ships Docker, because they `require` it. |
| D2 | M4-owned modules get `per_os = OsMap(macos=MacosPending("M4", workaround))`. `MacosPending.install` raises `NeedsUser`, so a Mac run reports `blocked: not automated on macOS yet (lands in M4)` with a manual workaround, and never runs `systemctl`/`dnf`. The contract test counts `MacosPending` as **unresolved**, so these names stay in `KNOWN_GAPS`. | Without it, `devboost install macos` would run Docker's Linux path on a Mac. M4 replaces each `MacosPending` with the real strategy. |
| D3 | **Homebrew ordering** is explicit: `PackageModule.requires = (Homebrew,)`, `FlatpakApp.requires = (Flatpak, Homebrew)`, and every module whose `per_os.macos` uses brew lists `Homebrew`. A strategy that uses brew says so with `uses_brew: ClassVar[bool] = True` (`BrewFormula`/`BrewCask` have it); a contract test fails for any brew-using module whose dependency closure lacks `homebrew`. The install log's "+N required dependencies added" now lists only modules that are **in the plan**, so Linux runs never mention `homebrew`/`xcode-clt`. | Spec §1. A test is the only way to keep 50+ modules honest. |
| D4 | `xcode-clt` installs silently the way Homebrew's own installer does: create `/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress`, pick the newest `Command Line Tools …` label from `softwareupdate --list`, `softwareupdate --install <label>`, `xcode-select --switch /Library/Developer/CommandLineTools`, remove the placeholder. No label offered → `NeedsUser` (`xcode-select --install`). The label is parsed in Python (`clt_label`), so it is unit-tested. | Spec §2 ("softwareupdate silent CLT install"). |
| D5 | `homebrew`: when `brew --prefix` is not `/opt/homebrew`, the official `install.sh` is downloaded into a private `mktemp -d` directory and run with `NONINTERACTIVE=1` (M1's sudo keepalive supplies the cached sudo it needs); then `brew analytics off`. Verify: prefix is `/opt/homebrew` **and** `brew analytics state` says `analytics are disabled`. An existing brew is never reinstalled; only analytics are turned off. The download-then-run step is one shared helper, `primitives/remote_script.run_script`, also used by `dotnet-sdk`. | Spec §2. Download-then-run (Z1's pattern) fails loudly on a failed download instead of piping nothing into bash. On this Mac analytics are currently **enabled** (`InfluxDB analytics are enabled.`). |
| D6 | `rosetta` verifies with `arch -x86_64 /usr/bin/true` (fails with "Bad CPU type" when Rosetta is absent, checked on this Mac) and installs with `sudo softwareupdate --install-rosetta --agree-to-license`. On macOS ≥ 28 verify is true (nothing to install) and `devboost doctor` reports "Rosetta limited" with the Intel-only apps (`system_profiler -json SPApplicationsDataType`, `arch_kind == "arch_i64"`; `arch_arm` / `arch_arm_i64` seen on this Mac). | Spec §0. The doctor check is informational (never fails). |
| D7 | **Cask upgrades on `--update`** (carry-over): `pkg.upgrade_cask` → `brew upgrade --cask <c>`. Homebrew 7.0.4's `cask/upgrade.rb` treats a **named** cask as `greedy: true`, which would re-download apps that update themselves, against spec §6. So `BrewCask.install` under `ctx.force` checks `pkg.cask_auto_updates` (`brew info --json=v2 --cask`) first and skips those. `FlatpakApp`'s macOS branch goes through `BrewCask`. On macOS, `--update` keeps every brew-backed module (`PackageModule`, `FlatpakApp` with a cask, a `BrewFormula`/`BrewCask` `per_os.macos`) as well as `self_updating` ones; Linux keeps today's `self_updating` filter. | Spec §6: "Casks with `auto_updates` update themselves — no `--greedy`". |
| D8 | **Pinned assets are keyed by `<os>-<arch>`** (carry-over): `linux-x86_64`, `linux-aarch64`, `macos-aarch64`, built by `media.catalog.asset_key(os_info)` and validated at load. There is no fallback between keys, so a Mac never gets a Linux binary. | Carry-over M3 item 2. |
| D9 | **herdr pin 0.7.5 → 0.9.1 on every OS**, URLs on `github.com/herdrdev/herdr` (the repo moved; SHA-256 digests from the GitHub release API). 0.7.5's macOS `herdr --remote` client disconnects right after the handshake (fixed in 0.8.x, herdr #2478), and client and server should run the same release across the fleet. `Herdr.verify` now also checks `herdr --version` ≥ the pin, so Linux boxes pick up the bump, and a newer self-updated herdr is never downgraded. homebrew-core has a `herdr` formula (0.9.1), but the pin stays: it is SHA-verified like Linux and keeps the pinned plugin set matched to one herdr release. | Spec §2 ("herdr pins"), §3 (remote image paste). |
| D10 | herdr's install script is BSD-safe: `shasum -a 256 -c -` on macOS (`sha256sum` on Linux), `mkdir -p` + `install -m 755` instead of GNU `install -D`. `keys.remote_image_paste = "ctrl+v"` is written explicitly into `dotfiles/dot_config/herdr/config.toml` (it is herdr's default since 0.7.1; explicit so a later default change cannot silently break image paste, which no terminal binds). | Spec §2 herdr row; M2 D18 handed the key to M3. |
| D11 | `glow` on Debian/Ubuntu comes from Charm's apt repo (`https://repo.charm.sh/apt/ * *`, key `https://repo.charm.sh/apt/gpg.key`, glow README). Ubuntu 24.04 has no `glow`; 26.04 ships 2.1.1. Fedora and Arch have `glow` 3.0.0 in their own repos. | Spec §2: `glow` in `cli` on **every OS**. |
| D12 | `dotnet-sdk` on macOS: `dotnet-install.sh --channel 10.0 --install-dir ~/.dotnet` (MIT, no sudo, same 10.0 pin as Linux); verify `~/.dotnet/dotnet --list-sdks` has a `10.` line. The executor puts `~/.dotnet` on PATH on Darwin (so `aspire` / `dotnet-lsp`'s `dotnet tool install` work in the same run), and `env.sh` exports `DOTNET_ROOT=$HOME/.dotnet` on Darwin when `~/.dotnet/dotnet` exists (a .NET app host does not search PATH; without it `csharp-ls` and `aspire` fail to start). | Spec §2 dotnet-sdk row. |
| D13 | `android-sdk` on macOS: `java@temurin-17` via mise (as Linux), cask `android-commandlinetools` (its `sdkmanager` lands in `/opt/homebrew/bin`), then the same `platform-tools`, `platforms;android-35`, `build-tools;35.0.0` into `$ANDROID_HOME` (default `~/Library/Android/sdk`, exported by M2's `env.sh`). No `/etc/profile.d`. | Spec §2 android-sdk row. |
| D14 | `ddev` on macOS: `brew tap ddev/ddev`, `brew install ddev/ddev/ddev` (not in homebrew-core, checked), `brew install mkcert`, then `mkcert -install` **only in an interactive run** (macOS asks for the password to trust the CA); otherwise `NeedsUser`. Verify: both formulae installed and `$(mkcert -CAROOT)/rootCA.pem` exists. `ddev-remote` is portable (a no-op on a non-headless host). | Spec §2 ddev row and §1 "Errors" (`mkcert -install` without a prompt → `NeedsUser`). |
| D15 | `tailscale` on macOS: cask `tailscale-app` (standalone variant, a `.pkg`). Its CLI is reached through a two-line wrapper `~/.local/bin/tailscale` that `exec`s `/Applications/Tailscale.app/Contents/MacOS/Tailscale` (Tailscale KB 1080 recommends calling the app binary by that path; a wrapper keeps the real executable path, which a symlink would not). Verify: cask, wrapper, and `status --json` `BackendState == "Running"`. Else: `up --authkey=…` when the bundle has `TAILSCALE_AUTHKEY` and the state is `NeedsLogin` (no `--ssh`: the Mac is a fleet client; no sudo); otherwise `open -a Tailscale` and `NeedsUser` with the approval steps. | Spec §2 tailscale row, spec §1 "Errors" (network-extension approval → `NeedsUser`). |
| D16 | **Default apps use `utiluti`, not `duti`** (spec deviation). `duti` is unmaintained (last push 2023-07; its upstream build fails on darwin25+, open PR #64; open bug #56: reassociation does not take effect on double-click). `utiluti` is Apache-2.0, released 1.5 on 2026-03-15, in homebrew-core with an arm64 bottle. The new module is `utiluti` (`families = ("macos",)`). | Spec §2 lists `duti`; the facts changed. |
| D17 | **macOS 26.4+ asks the user to confirm every default-app change** (one dialog per file type, the tool waits for the answer; scriptingosx.com, 2026-03; utiluti README). So `primitives/default_apps` (a) changes a type only when someone can answer (`is_interactive()`, or macOS < 26.4 where no dialog appears), (b) asks once per UTI (extensions that share a UTI share one dialog), and (c) records every extension it has handled in `~/.local/state/devboost/default-apps.json`, so a "no" is never asked again. A non-interactive run leaves Zed's config done and raises `NeedsUser` for the associations. M5's `default-apps` module reuses the primitive and the table `data/macos/default-apps.tsv`; Z2 ships only the Zed rows. | Zed spec "Default apps (macOS)"; carry-over Z2 item 2 (shared mechanism, no duplication). |
| D18 | The Zed rows in `data/macos/default-apps.tsv` cover source and config files a developer double-clicks: `md txt json yaml yml toml sh zsh py js mjs jsx ts tsx php cs css scss sql log`. `.ts` also names MPEG transport-stream video on macOS; on a dev box that trade is accepted and documented. | One confirmation per UTI on 27 (about 20). |
| D19 | The `$EDITOR`/`$VISUAL` override hook (carry-over Z2 item 3) is `~/.config/devboost/local.sh`, sourced **last** by `env.sh`, so it applies in bash, zsh and `bash -lc` launchers. It is the user's file: chezmoi does not manage it and dev-boost never writes it. The M2 plan as written adds only `~/.zshrc.local` / `~/.zprofile.local` (zsh-only, and after `env.sh`); Task 0 checks whether M2's execution added a `local.sh` hook and Task 14 adds it only if absent. | Carry-over Z2: "verify, don't duplicate". |
| D20 | Modules marked **`portable = True`** (verified to run unchanged on macOS; each gets a one-line reason in code): `claude-code`, `claude-mcp`, `claude-plugins`, `claude-skills`, `claude-notify`, `codex-code` (its `install.sh` handles `darwin/aarch64`, checked), `codex-config`, `codex-mcp`, `codex-plugins`, `codex-skills`, `pi-harness`, `tpm`, `tmux-persist`, `web-runtimes`, `devops-tools` (aqua has darwin-arm64 builds), `expo`, `data-services`, `aspire`, `dotnet-lsp`, every `LspModule` (`fresh-lsp`, `python-lsp`, `web-lsp`, `laravel-lsp`, `devops-lsp`), `herdr`, `herdr-plugins`, `chezmoi-repo`, `ddev-remote`, `playwright`. | Contract rule: `portable` needs a verified reason. |
| D21 | `chezmoi-repo` runs `chezmoi init --apply --force <repo>` on every OS, and a missing repo URL is `NeedsUser` (was `SecretsError` → `fail`). | Spec §2 chezmoi-repo row ("also fixes a Linux tty hang"). |
| D22 | Families / provided-by sweep. Linux-only (`families = LINUX_FAMILIES`, a new `core.osinfo` constant `("fedora", "debian", "arch")`): `agent-sudo`, `browser-view`, `caddy`, `code-server`, `crossarch-build`, `earlyoom`, `gpu-detect`, `zram`, `gearlever`. `provided_by` gains `"macos"`: `flameshot`, `fwupd`, `thermald`, `power-profiles-daemon`, `va-hwaccel`. `agent-sudo` and `gearlever` are not in the spec's list: `agent-sudo` is a server/brain feature ("Mac as a brain host" is out of scope) and Gear Lever manages AppImages. | Spec §2 families / provided-by lists. |
| D23 | `claude-notify`'s hook shows a native notification on Darwin **in addition to** ntfy, and without needing `DEVBOOST_NTFY_URL`. Title and cwd reach AppleScript as `on run argv` arguments, never spliced into the script, so a quote in a path cannot break it. | Spec §2 claude-notify row. |
| D24 | `ffmpeg-full` gains a macOS path (`families = ("fedora", "macos")`, brew `ffmpeg`). `multimedia` stays out of the `macos` profile; `devboost install multimedia` works on a Mac. | Spec §2 formulae ("ffmpeg-full → ffmpeg"). |
| D25 | The `macos` profile becomes the spec §2 list **minus `macos-desktop`**, which M5 creates and appends. | M3 must not reference a profile that does not exist yet. |
| D26 | `build-tools` on macOS: requires `xcode-clt` (clang, make, git) and installs brew `cmake` (the one tool of its Linux set that the CLT lacks and builds need). | Spec §2 build-tools row. |
| D27 | `playwright` on macOS skips the system-library step (Chromium for macOS bundles its own frameworks); browsers and the MCP registration are unchanged. | Spec §2 playwright row. |
| D28 | `devboost.lock` is not regenerated (as M2 D20). | Unrelated diff. |

**Pre-validation.** The snippets were written against the M2 plan's interfaces (`_brew.py`, `os_strategy`, `install_linux`/`verify_linux`, the `plan._supported` fallback) and against `main` @ `655be95` (M1 + P1 + Z1). M2 was still being executed when this plan was written, so the snippets were **not** run. If one fails, first suspect drift from M2 or P2 (Task 0), not the snippet.

---
## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/exec/userpaths.py` (create) | `mise_shims(home)`, `dotnet_root(home)` — one answer for the executor and config writers | 1 |
| `engine/src/devboost/exec/executor.py`, `engine/src/devboost/modules/_zed.py` (modify) | PATH uses the resolved mise shims; `~/.dotnet` on Darwin; `_zed.mise_shims` is the shared helper | 1 |
| `engine/src/devboost/exec/primitives/pkg.py` (modify) | `Brew.upgrade_cask`, `Brew.cask_auto_updates`; public `upgrade_cask`, `cask_auto_updates` | 2 |
| `engine/src/devboost/modules/_brew.py` (modify) | `BrewCask` honours `ctx.force` (upgrade unless the cask updates itself); `uses_brew` marker | 2 |
| `engine/src/devboost/modules/apps.py` (modify) | `FlatpakApp` macOS branch through `BrewCask`; casks for obsidian/bruno/bitwarden/localsend/vlc; `gearlever` Linux-only; `flameshot` provided on macOS; `ObsidianSync` pending | 2, 4, 5, 6, 7 |
| `engine/src/devboost/cli/app.py` (modify) | `--update` keeps brew-backed modules on macOS; dependency log lists planned modules only | 2, 4 |
| `engine/src/devboost/exec/primitives/remote_script.py` (create) | `run_script`: download an installer into a private temp dir, then run it | 3 |
| `engine/src/devboost/modules/macos.py` (create) | `XcodeClt`, `Homebrew`, `Rosetta`; `clt_label`, `mac_major`, `rosetta_supported`, `rosetta_present`, `intel_only_apps` | 3 |
| `engine/src/devboost/cli/doctor.py` (modify) | `rosetta` check on macOS | 3 |
| `engine/src/devboost/modules/_pkgmodule.py` (modify) | `requires = (Homebrew,)` | 4 |
| `engine/src/devboost/modules/{ripgrep,base,mise,editors,shell}.py` (modify) | M2's brew-backed modules require `Homebrew` | 4 |
| `engine/src/devboost/modules/_pending.py` (create) | `MacosPending` strategy | 5 |
| `engine/src/devboost/modules/{docker,dev_hygiene,system,server}.py` (modify) | M4-owned modules declare `MacosPending` | 5 |
| `engine/src/devboost/core/osinfo.py` (modify) | `LINUX_FAMILIES` | 6 |
| `engine/src/devboost/modules/{server,browser_view,caddy,code_server,crossarch_build,system,multimedia}.py` (modify) | families / provided-by sweep | 6 |
| `engine/src/devboost/modules/{editors,optional,mosh,dev_stacks,system,base,multimedia}.py` (modify) | formula / cask `per_os.macos` for vscode, jetbrains-toolbox, neovim, mosh, uv, smartmontools, build-tools, ffmpeg-full | 7 |
| `catalog.toml`, `engine/src/devboost/media/catalog.py`, `engine/src/devboost/modules/herdr.py`, `dotfiles/dot_config/herdr/config.toml` (modify) | `<os>-<arch>` pins, herdr 0.9.1, BSD-safe install, version-aware verify, `remote_image_paste`, `herdr-plugins` in `cli` | 8 |
| `engine/src/devboost/modules/cli_tools.py` (modify) | new `Glow` (Charm apt repo on Debian) and `Utiluti` | 8, 12 |
| `engine/src/devboost/modules/dev_stacks.py` (modify) | `dotnet-sdk` via `dotnet-install.sh`, `android-sdk` via the cmdline-tools cask; portable flags | 9, 10, 11 |
| `engine/src/devboost/modules/ddev.py`, `modules/server.py` (`Tailscale`), `modules/dev_stacks.py` (`Playwright`) (modify) | ddev tap + mkcert; Tailscale app + CLI wrapper + approval; Playwright without dnf | 10 |
| `engine/src/devboost/modules/{claude_*,codex_*,pi_harness,tpm,_lsp,base,shell}.py` (modify) | portable flags, credential wording, `chezmoi init --force` + `NeedsUser` | 11 |
| `dotfiles/private_dot_claude/hooks/executable_notify.sh` (modify) | native macOS notification | 11 |
| `engine/src/devboost/exec/primitives/default_apps.py` (create), `data/macos/default-apps.tsv` (create) | default apps via `utiluti`, one dialog per UTI, asked-once state — shared with M5 | 12 |
| `engine/src/devboost/modules/_zed.py`, `engine/src/devboost/modules/editors.py` (`Zed`) (modify); `dotfiles/.chezmoiignore` (modify only if M2 left a `.config/zed` Darwin ignore) | Zed on macOS: cask, config, default apps | 13 |
| `dotfiles/dot_config/devboost/env.sh` (modify) | `DOTNET_ROOT` on Darwin; `local.sh` override hook | 14 |
| `profiles.toml` (modify) | `base` += xcode-clt/homebrew/rosetta; `cli` += herdr-plugins/glow; `macos` = the workstation | 3, 8, 15 |
| `engine/tests/core/test_macos_contract.py` (modify) | pending ≠ resolved; Homebrew edges; `KNOWN_GAPS` owners; the `macos` profile plan | 4, 5, 15 |
| `docs/macos.md`, `docs/zed.md`, `docs/adding-a-module.md`, `docs/agents.md`, `docs/remote-fleet.md`, `README.md`, `CHANGELOG.md`, both specs (modify) | docs | 16 |

Tests created: `tests/exec/test_userpaths.py` (1), `tests/modules/test_cask_update.py` (2), `tests/modules/test_macos_base.py` (3), `tests/core/test_homebrew_edges.py` (4), `tests/modules/test_macos_pending.py` (5), `tests/modules/test_macos_sweep.py` (6), `tests/modules/test_macos_formulae_casks.py` (7), `tests/modules/test_herdr_macos.py` + `tests/modules/test_glow.py` (8), `tests/modules/test_dotnet_android_macos.py` (9), `tests/modules/test_ddev_tailscale_macos.py` (10), `tests/modules/test_portable_macos.py` + `tests/dotfiles/test_claude_notify.py` (11), `tests/primitives/test_default_apps.py` (12), `tests/modules/test_zed_macos.py` (13), `tests/dotfiles/test_env_overrides.py` (14).

---

### Task 0: Branch, baseline, shared-file re-check against main + M2

M2 is executed on `feat/macos-m2-shell` while this plan is written; P2 (pass on macOS) runs in parallel. Both touch files this plan edits. This task records what is actually there, so later tasks merge onto it.

**Files:** none (environment only)

- [ ] **Step 1: Branch from M2's head** (repo root). If M2 has merged to `main`, branch from `origin/main` instead.

```bash
git fetch origin
git log --oneline -3 origin/feat/macos-m2-shell origin/main
git checkout -b feat/macos-m3-z2-catalog origin/feat/macos-m2-shell   # or origin/main once M2 merged
```

- [ ] **Step 2: Confirm the M2 seams exist** (from `engine/`). Every task builds on them; stop and report if one is missing.

```bash
cd engine && uv sync
grep -n 'class BrewFormula\|class BrewCask' src/devboost/modules/_brew.py
grep -n 'def os_strategy' src/devboost/model.py
grep -n 'cls.install is not Module.install' src/devboost/core/plan.py
grep -n 'def install_linux\|def verify_linux\|def brew_strategy' src/devboost/modules/_pkgmodule.py
grep -n 'per_os = OsMap(macos=' -r src/devboost/modules | sort
```
Expected: both strategy classes, `os_strategy`, the plan fallback line, the three `PackageModule` hooks, and `per_os` lines at least for `ripgrep`, `chezmoi`, `mise`, `starship`, `fresh`, `ghostty`, `wezterm`, `nerd-fonts`, `zsh-plugins`. Write the `per_os` list down: Task 4 adds `Homebrew` to exactly those modules.

- [ ] **Step 3: Baseline gate**

```bash
uv run ruff check && uv run mypy && uv run pytest -q 2>&1 | tail -3
```
Expected: all green. If red on the branch point, stop and report; M3 must start green.

- [ ] **Step 4: Re-check the shared files** and write down what you see:

```bash
grep -n 'local.sh\|LANG=\|ANDROID_HOME\|DOTNET' ../dotfiles/dot_config/devboost/env.sh
grep -n 'zed' ../dotfiles/.chezmoiignore
grep -nE '^(macos|base|cli|shell|terminal|editors|optional-terminals) ' ../profiles.toml
grep -n 'LINUX_FAMILIES\|("fedora", "debian", "arch")' -r src/devboost | head
grep -n '"pass"' tests/core/test_macos_contract.py src/devboost/cli/host.py
grep -c '^    "' tests/core/test_macos_contract.py
git log --oneline origin/main -10 | grep -i 'pass\|p2' || true
```

Record:
- **`local.sh`** — if `env.sh` already sources `~/.config/devboost/local.sh`, Task 14 keeps that hook and adds only the test (D19).
- **`.config/zed` in `.chezmoiignore`** — if M2 left it in the Darwin block, Task 13 Step 3 removes it; otherwise that step is a no-op.
- **`LINUX_FAMILIES`** — if M2 already added an equivalent constant (e.g. for `bash-config`), Task 6 reuses that name instead of adding a second one.
- **P2** — if P2 has merged (`"pass"` gone from `LINUX_ONLY`, `pass` resolvable), `"pass"` is no longer a gap: drop it from the final `KNOWN_GAPS` in Task 15 and from D1's list in Task 16.
- **`KNOWN_GAPS`** — note the names. Tasks 6–11 delete names from it; each task lists them.

No commit.

---
### Task 1: Shared user paths — mise shims resolved once, `~/.dotnet` on the Darwin PATH

Carry-over M3 item 4: `executor._prepend_mise_dirs` hard-codes `~/.local/share/mise/shims`, while Z1's `_zed.mise_shims` already resolves `$MISE_DATA_DIR` → `$XDG_DATA_HOME/mise` → `~/.local/share/mise` like mise does. The executor (exec layer) cannot import a module helper, so the helper moves to the exec layer and `_zed` reuses it.

**Files:**
- Create: `engine/src/devboost/exec/userpaths.py`
- Modify: `engine/src/devboost/exec/executor.py` (`_prepend_mise_dirs`), `engine/src/devboost/modules/_zed.py` (`mise_shims`)
- Test: `engine/tests/exec/test_userpaths.py` (create)

**Interfaces:**
- Produces: `userpaths.mise_shims(home: Path) -> Path`; `userpaths.dotnet_root(home: Path) -> Path` (`home / ".dotnet"`). `_zed.mise_shims` is the same object as `userpaths.mise_shims`. On Darwin, `_prepend_mise_dirs` adds `~/.dotnet` (after `~/.dotnet/tools`, before Homebrew).

- [ ] **Step 1: Write the failing tests** — `tests/exec/test_userpaths.py`

```python
"""One answer for where mise's shims and the user .NET SDK live."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from devboost.exec import userpaths
from devboost.exec.executor import _prepend_mise_dirs
from devboost.modules import _zed


def test_mise_shims_prefer_mise_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "m"))
    assert userpaths.mise_shims(tmp_path) == tmp_path / "m" / "shims"


def test_mise_shims_then_xdg_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "x"))
    assert userpaths.mise_shims(tmp_path) == tmp_path / "x" / "mise" / "shims"


def test_mise_shims_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "")  # empty counts as unset, as in mise
    assert userpaths.mise_shims(tmp_path) == tmp_path / ".local" / "share" / "mise" / "shims"


def test_executor_path_uses_the_resolved_shims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "m"))
    parts = _prepend_mise_dirs("/usr/bin", system="Linux").split(os.pathsep)
    assert parts[0] == str(tmp_path / "m" / "shims")
    assert str(tmp_path / ".local" / "share" / "mise" / "shims") not in parts


def test_darwin_path_has_the_user_dotnet_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    dotnet = str(tmp_path / ".dotnet")
    mac = _prepend_mise_dirs("/usr/bin", system="Darwin").split(os.pathsep)
    assert mac.index(str(tmp_path / ".dotnet" / "tools")) < mac.index(dotnet)
    assert mac.index(dotnet) < mac.index("/opt/homebrew/bin") < mac.index("/usr/bin")
    assert dotnet not in _prepend_mise_dirs("/usr/bin", system="Linux").split(os.pathsep)


def test_zed_reuses_the_shared_helper() -> None:
    assert _zed.mise_shims is userpaths.mise_shims
    assert userpaths.dotnet_root(Path("/h")) == Path("/h/.dotnet")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/exec/test_userpaths.py -v`
Expected: FAIL with `ImportError: cannot import name 'userpaths' from 'devboost.exec'`.

- [ ] **Step 3: Implement**

Create `engine/src/devboost/exec/userpaths.py`:

```python
"""Where per-user tool directories live — one answer for the executor and config writers.

Lives in the exec layer so ``executor.py`` can use it; modules (e.g. ``_zed``) import it
from here rather than keeping their own copy.
"""

from __future__ import annotations

import os
from pathlib import Path


def mise_shims(home: Path) -> Path:
    """mise's shim dir, resolved the way mise resolves its data dir: ``$MISE_DATA_DIR``,
    then ``$XDG_DATA_HOME/mise``, then ``~/.local/share/mise`` (an empty variable counts as
    unset)."""
    data = os.environ.get("MISE_DATA_DIR")
    if data:
        return Path(data) / "shims"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "mise" / "shims"


def dotnet_root(home: Path) -> Path:
    """The per-user .NET SDK that ``dotnet-install.sh`` writes on macOS (dotnet-sdk module)."""
    return home / ".dotnet"
```

In `engine/src/devboost/exec/executor.py`, add `from devboost.exec import userpaths` to the imports and replace `_prepend_mise_dirs`:

```python
def _prepend_mise_dirs(path: str, system: str | None = None) -> str:
    """Return *path* with the user tool dirs prepended (if not already present).

    Ensures tools found in subprocesses even on a fresh firstboot where the user's shell
    profile has not been sourced: ``mise`` shims (node, pnpm, bun, …), ``~/.local/bin``, and
    ``~/.dotnet/tools`` (where ``dotnet tool install -g`` puts aspire, csharp-ls, csharpier).

    On macOS a ``curl | bash`` run has no brew shellenv yet, so Homebrew's prefix is
    added too — brew and everything it installs resolve without a new login shell — and so
    is ``~/.dotnet``, where the dotnet-sdk module installs the SDK on macOS.
    """
    try:
        home = Path.home()
    except RuntimeError:
        return path
    prepend = [
        str(userpaths.mise_shims(home)),
        str(home / ".local" / "bin"),
        str(home / ".dotnet" / "tools"),
    ]
    if (system or platform.system()) == "Darwin":
        prepend.append(str(userpaths.dotnet_root(home)))
        prepend.extend(_HOMEBREW_DIRS)
    existing = path.split(os.pathsep) if path else []
    new_parts = [p for p in prepend if p not in existing]
    return os.pathsep.join([*new_parts, *existing]) if new_parts else path
```

In `engine/src/devboost/modules/_zed.py`: delete the whole `def mise_shims(home: Path) -> Path:` function and add to the imports:

```python
from devboost.exec.userpaths import mise_shims
```

(`lsp_binaries` keeps calling `mise_shims(home)`; Z1's `tests/modules/test_zed_config.py::test_mise_shims_*` keep passing through this import.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/exec tests/modules/test_zed_config.py -v && uv run mypy && uv run ruff check`
Expected: PASS, including the existing `test_prepend_mise_dirs_*` and `test_darwin_path_includes_homebrew_after_user_dirs`.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/userpaths.py src/devboost/exec/executor.py src/devboost/modules/_zed.py tests/exec/test_userpaths.py
git commit -m "fix(exec): resolve mise shims like mise does; user .NET SDK on the macOS PATH"
```

---

### Task 2: Casks upgrade on `--update`; apps that update themselves are left alone

Carry-over M3 item 1. Spec §6.

**Files:**
- Modify: `engine/src/devboost/exec/primitives/pkg.py` (`Brew`, public helpers), `engine/src/devboost/modules/_brew.py` (`BrewFormula`, `BrewCask`), `engine/src/devboost/modules/apps.py` (`FlatpakApp`), `engine/src/devboost/cli/app.py` (`_apply_update_filter`, `_run`)
- Test: `engine/tests/modules/test_cask_update.py` (create)

**Interfaces:**
- Consumes: `BrewCask`, `BrewFormula` (M2).
- Produces:
  - `pkg.upgrade_cask(ctx, *casks: str) -> None` → `brew upgrade --cask <casks>` (raises `UnsupportedOS` off macOS, `InstallError` on failure).
  - `pkg.cask_auto_updates(ctx, cask: str) -> bool` — from `brew info --json=v2 --cask <cask>`; `False` off macOS or on any parse error.
  - `BrewCask.install(ctx)`: without `ctx.force`, one `install_cask` (as M1/M2 — a no-op for an installed cask); with `ctx.force`: not installed → `install_cask`; installed → skip when `cask_auto_updates`, else `upgrade_cask`.
  - `BrewFormula.uses_brew` / `BrewCask.uses_brew`: `ClassVar[bool] = True` (read by Task 4's contract test).
  - `FlatpakApp` on macOS verifies and installs through `BrewCask(self.cask)`.
  - `cli.app._apply_update_filter(plan, modules, os_info: OsInfo | None = None)` and `cli.app._brew_managed_on_macos(cls) -> bool`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_cask_update.py`

```python
"""`--update` upgrades Homebrew casks, except apps that update themselves (spec §6)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from devboost.cli.app import _apply_update_filter, _brew_managed_on_macos
from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.plan import PlannedModule
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Brew(FakeExecutor):
    """Scripted brew: `list` succeeds for installed casks, `info` reports auto_updates."""

    def __init__(self, installed: set[str], auto_updates: set[str] | None = None) -> None:
        super().__init__()
        self.installed = installed
        self.auto_updates = auto_updates or set()

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:2]) == ["brew", "list"]:
            return Result(0) if argv[-1] in self.installed else Result(1)
        if list(argv[:2]) == ["brew", "info"]:
            cask = argv[-1]
            body = {"casks": [{"token": cask, "auto_updates": cask in self.auto_updates}]}
            return Result(0, stdout=json.dumps(body))
        return Result(0)


def test_upgrade_cask_argv_and_failure() -> None:
    ex = FakeExecutor()
    pkg.upgrade_cask(Ctx(os=MAC, ex=ex), "localsend")
    assert ex.calls == [["brew", "upgrade", "--cask", "localsend"]]
    failing = FakeExecutor(scripts={"brew": Result(1)})
    with pytest.raises(InstallError, match="brew upgrade --cask localsend"):
        pkg.upgrade_cask(Ctx(os=MAC, ex=failing), "localsend")
    with pytest.raises(UnsupportedOS):
        pkg.upgrade_cask(Ctx(os=FEDORA, ex=FakeExecutor()), "localsend")


def test_cask_auto_updates_reads_brew_info() -> None:
    ex = _Brew(installed={"zed"}, auto_updates={"zed"})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=ex), "zed") is True
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=_Brew(installed=set())), "vlc") is False
    garbage = FakeExecutor(scripts={"brew": Result(0, stdout="not json")})
    assert pkg.cask_auto_updates(Ctx(os=MAC, ex=garbage), "vlc") is False
    assert pkg.cask_auto_updates(Ctx(os=FEDORA, ex=FakeExecutor()), "vlc") is False


def test_force_upgrades_an_installed_cask_that_does_not_update_itself() -> None:
    ex = _Brew(installed={"localsend"})
    BrewCask("localsend").install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--cask", "localsend"]
    assert not any(c[:2] == ["brew", "install"] for c in ex.calls)


def test_force_leaves_a_self_updating_cask_alone() -> None:
    # A NAMED `brew upgrade --cask` is greedy in Homebrew 7 — it must not be called here.
    ex = _Brew(installed={"obsidian"}, auto_updates={"obsidian"})
    BrewCask("obsidian").install(Ctx(os=MAC, ex=ex, force=True))
    assert not any(c[:2] == ["brew", "upgrade"] for c in ex.calls)


def test_without_force_it_is_one_adopting_install() -> None:
    # Unchanged from M1/M2: installing an installed cask is a no-op in brew.
    ex = _Brew(installed={"vlc"})
    BrewCask("vlc").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "vlc"]]


def test_missing_cask_is_installed_even_under_force() -> None:
    ex = _Brew(installed=set())
    BrewCask("vlc").install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "install", "--cask", "-y", "--adopt", "vlc"]


def test_strategies_declare_they_use_brew() -> None:
    assert BrewCask.uses_brew is True
    assert BrewFormula.uses_brew is True


class _App(FlatpakApp):
    name: ClassVar[str] = "cask-update-probe"
    app_id: ClassVar[str] = "org.probe.App"
    cask: ClassVar[str | None] = "probe-app"


def test_flatpak_app_upgrades_its_cask_under_force() -> None:
    ex = _Brew(installed={"probe-app"})
    _App().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--cask", "probe-app"]


class _Custom(Module):
    name: ClassVar[str] = "custom-probe"
    per_os = OsMap(macos=BrewFormula("probe"))

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


class _Heavy(Module):
    name: ClassVar[str] = "heavy-probe"


def test_update_keeps_brew_backed_modules_on_macos_only() -> None:
    modules: dict[str, type[Module]] = {
        "cask-update-probe": _App, "custom-probe": _Custom, "heavy-probe": _Heavy,
    }
    plan = [PlannedModule(n) for n in modules]
    assert [p.name for p in _apply_update_filter(plan, modules, MAC)] == [
        "cask-update-probe", "custom-probe",
    ]
    assert _apply_update_filter(plan, modules, FEDORA) == []
    assert _apply_update_filter(plan, modules) == []  # no OS given: today's behaviour
    assert _brew_managed_on_macos(_Heavy) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_cask_update.py -v`
Expected: FAIL with `ImportError: cannot import name '_brew_managed_on_macos'`.

- [ ] **Step 3: Implement**

In `engine/src/devboost/exec/primitives/pkg.py`, add `import json` to the imports, then add two methods to `class Brew` after `upgrade`:

```python
    def upgrade_cask(self, ctx: Ctx, *casks: str) -> None:
        if not casks:
            return
        res = self._brew(ctx, "upgrade", "--cask", *casks)
        if not res.ok:
            raise InstallError("brew", f"brew upgrade --cask {' '.join(casks)}", res.code)

    def cask_auto_updates(self, ctx: Ctx, cask: str) -> bool:
        """True when the cask declares ``auto_updates`` (the app updates itself)."""
        res = self._brew(ctx, "info", "--json=v2", "--cask", cask)
        if not res.ok:
            return False
        try:
            return bool(json.loads(res.stdout)["casks"][0].get("auto_updates"))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return False
```

and after the public `upgrade` function:

```python
def upgrade_cask(ctx: Ctx, *casks: str) -> None:
    """Upgrade casks in place (`devboost install --update` on macOS)."""
    _brew_or_raise(ctx, "brew upgrade --cask").upgrade_cask(ctx, *casks)


def cask_auto_updates(ctx: Ctx, cask: str) -> bool:
    """True when the cask updates itself; always False off macOS (never raises)."""
    if ctx.os.family != "macos":
        return False
    return Brew().cask_auto_updates(ctx, cask)
```

In `engine/src/devboost/modules/_brew.py`: add `from typing import ClassVar` and `from devboost.core import log` to the imports; add

```python
    #: Read by the macOS contract test: a module using this strategy must require Homebrew.
    uses_brew: ClassVar[bool] = True
```

as the first statement of **both** class bodies (after the docstring); and replace `BrewCask.install`:

```python
    def install(self, ctx: Ctx) -> None:
        if not ctx.force or not pkg.cask_installed(ctx, self.cask):
            # `brew install --cask` of an installed cask is a no-op — no pre-check needed.
            pkg.install_cask(ctx, self.cask)
            return
        # A NAMED `brew upgrade --cask` is greedy in Homebrew 7 (cask/upgrade.rb): it would
        # re-download apps that update themselves. Spec §6 leaves those to the app.
        if pkg.cask_auto_updates(ctx, self.cask):
            log.skip(f"{self.cask}: updates itself — not upgraded by brew")
            return
        pkg.upgrade_cask(ctx, self.cask)
```

(`dataclass(frozen=True)` ignores `ClassVar` fields, so equality stays by name. Without `ctx.force` the behaviour is exactly M1/M2's — one `brew install --cask -y --adopt` — so their tests are untouched.)

In `engine/src/devboost/modules/apps.py`, add `from devboost.modules._brew import BrewCask` and replace the two macOS branches of `FlatpakApp`:

```python
    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "macos":
            return self.cask is not None and BrewCask(self.cask).verify(ctx)
        # ... the Arch and Flathub branches stay exactly as they are

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "macos":
            if self.cask is None:
                raise UnsupportedOS(f"{self.name}: no macOS cask declared (set cask)")
            BrewCask(self.cask).install(ctx)
            return
        # ... the Arch and Flathub branches stay exactly as they are
```

In `engine/src/devboost/cli/app.py` add `from devboost.core.osinfo import OsInfo` if it is not imported yet, then add the helper and replace `_apply_update_filter`:

```python
def _brew_managed_on_macos(cls: type[Module]) -> bool:
    """True when a module's whole macOS install is one Homebrew formula or cask.

    `brew upgrade` is safe for all of these; custom macOS strategies (the Android SDK,
    Tailscale, …) are provisioning steps and stay out of `--update`, as on Linux.
    """
    from devboost.modules._brew import BrewCask, BrewFormula
    from devboost.modules._pkgmodule import PackageModule
    from devboost.modules.apps import FlatpakApp

    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    if issubclass(cls, PackageModule):
        return True
    return isinstance(cls.per_os.macos, (BrewFormula, BrewCask))


def _apply_update_filter(
    plan: list[PlannedModule],
    modules: Mapping[str, type[Module]],
    os_info: OsInfo | None = None,
) -> list[PlannedModule]:
    """Keep only self-updating modules (single-package/binary tools safe to force-refresh).

    Non-self-updating modules are dropped from the plan entirely — `--update` must not
    install a heavy provisioning module, only refresh the CLI tools. On macOS every module
    that is exactly a Homebrew formula or cask is refreshed too (casks that update
    themselves are skipped by BrewCask).
    """
    on_mac = os_info is not None and os_info.family == "macos"
    return [
        pm
        for pm in plan
        if modules[pm.name].self_updating
        or (on_mac and _brew_managed_on_macos(modules[pm.name]))
    ]
```

and in `_run`: `plan = _apply_update_filter(plan, modules, ctx.os)`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_cask_update.py tests/modules/test_brew_strategies.py tests/modules/test_macos_contract_fields.py tests/modules/test_apps.py tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS. The existing `test_apply_update_filter_keeps_only_self_updating` still passes (no OS given).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/primitives/pkg.py src/devboost/modules/_brew.py src/devboost/modules/apps.py src/devboost/cli/app.py tests/modules/test_cask_update.py
git commit -m "feat(macos): --update upgrades casks, leaving apps that update themselves alone"
```

---

### Task 3: macOS foundation — `xcode-clt`, `homebrew`, `rosetta` (+ doctor)

**Files:**
- Create: `engine/src/devboost/exec/primitives/remote_script.py`, `engine/src/devboost/modules/macos.py`, `engine/tests/scripted.py` (shared test executor)
- Modify: `engine/src/devboost/cli/doctor.py`, `profiles.toml` (`base`)
- Test: `engine/tests/modules/test_macos_base.py` (create), `engine/tests/cli/test_doctor_macos.py` (append)

**Interfaces:**
- Produces:
  - `remote_script.run_script(ctx, who: str, url: str, interpreter: str, *args: str, env: Mapping[str, str] | None = None) -> None` — `mktemp -d`, `curl -fsSL --proto =https --tlsv1.2 -o <tmp>/install.sh <url>`, `<interpreter> <tmp>/install.sh <args…>`, then always `rm -rf <tmp>`; any failure → `InstallError(who, <argv>, code)`.
  - `modules.macos`: `XcodeClt` (`xcode-clt`), `Homebrew` (`homebrew`, requires `XcodeClt`), `Rosetta` (`rosetta`) — all `families = ("macos",)`, `profiles = ("base",)`. Helpers `clt_label(listing: str) -> str | None`, `mac_major(os_info: OsInfo) -> int` (0 when unknown), `rosetta_supported(os_info) -> bool`, `rosetta_present(ctx) -> bool`, `intel_only_apps(ctx) -> list[str]`; constants `CLT_PLACEHOLDER`, `CLT_DIR`, `BREW_INSTALLER`, `BREW_PREFIX`.
  - `tests/scripted.py`: `Scripted(FakeExecutor)` with `answers: dict[tuple[str, ...], Result]` (longest argv-prefix match wins, then `scripts`, then `Result(0)`), and per-call `envs` and `interactives` lists index-aligned with `calls`. Later tasks import it as `from tests.scripted import Scripted`.
  - `doctor` check `rosetta` on macOS (always `ok=True`, informational).

- [ ] **Step 1: Create the shared test executor** — `engine/tests/scripted.py`

```python
"""A FakeExecutor that answers by argv prefix — for code that calls one tool several ways."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import FakeExecutor, Result


@dataclass
class Scripted(FakeExecutor):
    """``answers`` maps an argv prefix to a Result; the longest matching prefix wins, then
    ``scripts`` (by argv[0]), then Result(0). ``envs`` / ``interactives`` record each call's
    ``env`` and ``interactive`` arguments, index-aligned with ``calls``."""

    answers: dict[tuple[str, ...], Result] = field(default_factory=dict)
    envs: list[Mapping[str, str] | None] = field(default_factory=list)
    interactives: list[bool] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        default = super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive
        )
        self.envs.append(env)
        self.interactives.append(interactive)
        key = tuple(argv)
        for n in range(len(key), 0, -1):
            if key[:n] in self.answers:
                return self.answers[key[:n]]
        return default
```

- [ ] **Step 2: Write the failing tests** — `tests/modules/test_macos_base.py`

```python
"""The macOS foundation: Command Line Tools, Homebrew, Rosetta 2 (spec §0, §2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import load_profiles
from devboost.core.registry import load
from devboost.exec.executor import Result
from devboost.exec.primitives import remote_script
from devboost.model import Ctx
from devboost.modules import macos
from devboost.modules.macos import Homebrew, Rosetta, XcodeClt, clt_label
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]

LISTING = (
    "Software Update Tool\n\nFinding available software\n"
    "Software Update found the following new or updated software:\n"
    "* Label: Command Line Tools for Xcode 26.4-26.4\n"
    "\tTitle: Command Line Tools for Xcode 26.4, Version: 26.4, Size: 900000KiB,\n"
    "* Label: Command Line Tools for Xcode 27.0-27.0\n"
    "\tTitle: Command Line Tools for Xcode 27.0, Version: 27.0, Size: 912000KiB,\n"
    "* Label: macOS Golden Gate 27.0.1-26A500\n"
)


def test_clt_label_picks_the_newest_command_line_tools() -> None:
    assert clt_label(LISTING) == "Command Line Tools for Xcode 27.0-27.0"
    assert clt_label("No new software available.") is None


def test_xcode_clt_installs_the_offered_label_and_cleans_up() -> None:
    ex = Scripted(answers={("softwareupdate", "--list"): Result(0, stdout=LISTING)})
    XcodeClt().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["sudo", "touch", macos.CLT_PLACEHOLDER],
        ["softwareupdate", "--list"],
        ["sudo", "softwareupdate", "--install", "Command Line Tools for Xcode 27.0-27.0"],
        ["sudo", "xcode-select", "--switch", macos.CLT_DIR],
        ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER],
    ]


def test_xcode_clt_without_an_offer_needs_the_user() -> None:
    ex = Scripted(answers={("softwareupdate", "--list"): Result(0, stdout="No new software")})
    with pytest.raises(NeedsUser, match="xcode-select --install"):
        XcodeClt().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER]


def test_xcode_clt_verify_asks_xcode_select() -> None:
    assert XcodeClt().verify(Ctx(os=MAC, ex=Scripted())) is True
    missing = Scripted(answers={("xcode-select", "-p"): Result(2)})
    assert XcodeClt().verify(Ctx(os=MAC, ex=missing)) is False


def _brew(prefix: str = "/opt/homebrew", state: str = "disabled") -> Scripted:
    return Scripted(answers={
        ("brew", "--prefix"): Result(0, stdout=f"{prefix}\n"),
        ("brew", "analytics", "state"): Result(0, stdout=f"InfluxDB analytics are {state}.\n"),
    })


def test_homebrew_verify_needs_the_prefix_and_analytics_off() -> None:
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew())) is True
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew(state="enabled"))) is False
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew(prefix="/usr/local"))) is False
    none = Scripted(answers={("brew",): Result(127)})
    assert Homebrew().verify(Ctx(os=MAC, ex=none)) is False


def test_existing_homebrew_only_gets_analytics_turned_off() -> None:
    ex = _brew(state="enabled")
    Homebrew().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "--prefix"], ["brew", "analytics", "off"]]


def test_missing_homebrew_runs_the_official_installer_noninteractively() -> None:
    ex = Scripted(answers={
        ("brew", "--prefix"): Result(127),
        ("mktemp", "-d"): Result(0, stdout="/tmp/db.1\n"),
    })
    Homebrew().install(Ctx(os=MAC, ex=ex))
    download = ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o", "/tmp/db.1/install.sh",
                macos.BREW_INSTALLER]
    assert download in ex.calls
    run = ex.calls.index(["/bin/bash", "/tmp/db.1/install.sh"])
    assert ex.envs[run] == {"NONINTERACTIVE": "1"}
    assert ex.calls[-2:] == [["rm", "-rf", "/tmp/db.1"], ["brew", "analytics", "off"]]
    assert not any(c[0] == "sudo" for c in ex.calls)  # brew refuses root; never sudo


def test_run_script_cleans_up_after_a_failed_download() -> None:
    ex = Scripted(answers={
        ("mktemp", "-d"): Result(0, stdout="/tmp/db.2\n"),
        ("curl",): Result(22),
    })
    with pytest.raises(InstallError, match="curl"):
        remote_script.run_script(Ctx(os=MAC, ex=ex), "probe", "https://x/i.sh", "sh")
    assert ex.calls[-1] == ["rm", "-rf", "/tmp/db.2"]
    assert not any(c[0] == "sh" for c in ex.calls)


def test_rosetta_on_27_verifies_by_running_an_intel_binary() -> None:
    absent = Scripted(answers={("arch",): Result(1, stderr="Bad CPU type in executable")})
    assert Rosetta().verify(Ctx(os=MAC, ex=absent)) is False
    assert Rosetta().verify(Ctx(os=MAC, ex=Scripted())) is True


def test_rosetta_from_28_has_nothing_to_install() -> None:
    ex = Scripted()
    assert Rosetta().verify(Ctx(os=MAC28, ex=ex)) is True
    assert ex.calls == []


def test_rosetta_install_accepts_the_licence_with_sudo() -> None:
    ex = Scripted()
    Rosetta().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["sudo", "softwareupdate", "--install-rosetta", "--agree-to-license"]]
    failing = Scripted(answers={("softwareupdate",): Result(1)})
    with pytest.raises(InstallError):
        Rosetta().install(Ctx(os=MAC, ex=failing))


def test_intel_only_apps_come_from_system_profiler() -> None:
    body = {"SPApplicationsDataType": [
        {"_name": "OldApp", "arch_kind": "arch_i64"},
        {"_name": "Safari", "arch_kind": "arch_arm"},
        {"_name": "Universal", "arch_kind": "arch_arm_i64"},
    ]}
    ex = Scripted(answers={("system_profiler",): Result(0, stdout=json.dumps(body))})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=ex)) == ["OldApp"]
    bad = Scripted(answers={("system_profiler",): Result(0, stdout="nope")})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=bad)) == []


def test_mac_major() -> None:
    assert macos.mac_major(MAC) == 27
    assert macos.mac_major(OsInfo("macos", "macos", "aarch64", version_id="26")) == 26
    assert macos.mac_major(OsInfo("macos", "macos", "aarch64")) == 0
    assert macos.rosetta_supported(MAC) and not macos.rosetta_supported(MAC28)


def test_the_foundation_is_macos_only_and_in_base(tmp_path: Path) -> None:
    for cls in (XcodeClt, Homebrew, Rosetta):
        assert cls.families == ("macos",) and cls.profiles == ("base",)
    assert XcodeClt in Homebrew.requires
    names = ["xcode-clt", "homebrew", "rosetta"]
    assert build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "x") == []
    base = load_profiles(REPO_ROOT / "profiles.toml")["base"]
    assert set(names) <= set(base)
```

Append to `tests/cli/test_doctor_macos.py` (add `import json` to its imports):

```python
def test_rosetta_check_says_how_to_install_it(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44), "arch": Result(1)})
    checks = {c.name: c for c in run_checks(Ctx(os=MAC, ex=ex), tmp_path)}
    assert checks["rosetta"].ok is True
    assert "devboost install rosetta" in checks["rosetta"].detail


def test_rosetta_check_lists_intel_only_apps_from_28(tmp_path: Path) -> None:
    body = json.dumps({"SPApplicationsDataType": [{"_name": "OldApp", "arch_kind": "arch_i64"}]})
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44), "system_profiler": Result(0, stdout=body)})
    mac28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
    checks = {c.name: c for c in run_checks(Ctx(os=mac28, ex=ex), tmp_path)}
    assert checks["rosetta"].ok is True and "OldApp" in checks["rosetta"].detail


def test_no_rosetta_check_on_linux(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "age"})
    assert "rosetta" not in _names(Ctx(os=FEDORA, ex=ex), tmp_path)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_base.py tests/cli/test_doctor_macos.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules.macos'`.

- [ ] **Step 4: Implement**

Create `engine/src/devboost/exec/primitives/remote_script.py`:

```python
"""Run an upstream installer script: download it into a private temp dir, then run it.

Download-then-run (never `curl | sh`) makes a failed download fail loudly instead of
piping nothing into the shell. The `mktemp -d` dir is made through the executor (0700; a
demoting executor makes it the target user's), so nothing lands at a guessable /tmp path.
"""

from __future__ import annotations

from collections.abc import Mapping

from devboost.core.errors import InstallError
from devboost.model import Ctx

_DOWNLOAD = ("curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o")


def run_script(
    ctx: Ctx,
    who: str,
    url: str,
    interpreter: str,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> None:
    """Download *url* and run it as ``<interpreter> <script> <args…>`` (with *env*)."""
    mk = ctx.ex.run(["mktemp", "-d"])
    tmp = mk.stdout.strip()
    if not mk.ok or not tmp.startswith("/"):
        raise InstallError(who, "mktemp -d", mk.code or 1)
    script = f"{tmp}/install.sh"
    try:
        for argv in ([*_DOWNLOAD, script, url], [interpreter, script, *args]):
            res = ctx.ex.run(argv, env=env)
            if not res.ok:
                raise InstallError(who, " ".join(argv), res.code)
    finally:
        ctx.ex.run(["rm", "-rf", tmp])
```

Create `engine/src/devboost/modules/macos.py`:

```python
"""macOS foundations: Command Line Tools, Homebrew, Rosetta 2 (spec §0, §2).

Every module whose macOS install uses Homebrew `requires` Homebrew, which requires the
CLT. All three are `families = ("macos",)`, so Linux plans drop them.
"""

from __future__ import annotations

import json
import re
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.exec.primitives import remote_script
from devboost.exec.primitives.pkg import BREW_ENV
from devboost.model import Ctx, Module

_MACOS: tuple[str, ...] = ("macos",)

CLT_DIR = "/Library/Developer/CommandLineTools"
#: While this file exists, `softwareupdate --list` offers the CLT (Homebrew's installer
#: uses the same trick); otherwise only the GUI prompt of `xcode-select --install` does.
CLT_PLACEHOLDER = "/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress"
BREW_INSTALLER = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
BREW_PREFIX = "/opt/homebrew"
#: Rosetta 2 is fully available through macOS 27; from 28 Apple limits it to legacy games.
ROSETTA_LAST_FULL_MAJOR = 27

_LABEL = re.compile(r"^\s*\*\s*Label:\s*(Command Line Tools.*?)\s*$")


def clt_label(listing: str) -> str | None:
    """The newest "Command Line Tools …" label in `softwareupdate --list` output."""
    labels = [m.group(1) for line in listing.splitlines() if (m := _LABEL.match(line))]
    if not labels:
        return None
    return max(labels, key=lambda label: tuple(int(n) for n in re.findall(r"\d+", label)))


def mac_major(os_info: OsInfo) -> int:
    """The macOS major version ("27.0" → 27); 0 when unknown."""
    head = os_info.version_id.split(".", 1)[0]
    return int(head) if head.isdigit() else 0


def rosetta_supported(os_info: OsInfo) -> bool:
    major = mac_major(os_info)
    return major == 0 or major <= ROSETTA_LAST_FULL_MAJOR


def rosetta_present(ctx: Ctx) -> bool:
    # Fails with "Bad CPU type in executable" when Rosetta is not installed.
    return ctx.ex.run(["arch", "-x86_64", "/usr/bin/true"]).ok


def intel_only_apps(ctx: Ctx) -> list[str]:
    """Installed apps that are Intel-only (they need Rosetta)."""
    res = ctx.ex.run(["system_profiler", "-json", "SPApplicationsDataType"])
    if not res.ok:
        return []
    try:
        items = json.loads(res.stdout).get("SPApplicationsDataType", [])
    except (ValueError, AttributeError):
        return []
    return sorted({
        str(i["_name"])
        for i in items
        if isinstance(i, dict) and i.get("arch_kind") == "arch_i64" and "_name" in i
    })


@register
class XcodeClt(Module):
    name = "xcode-clt"
    category = "base"
    description = "Xcode Command Line Tools (clang, make, git) — installed without a dialog."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["xcode-select", "-p"]).ok

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["touch", CLT_PLACEHOLDER], sudo=True)
        try:
            listing = ctx.ex.run(["softwareupdate", "--list"])
            label = clt_label(listing.stdout + "\n" + listing.stderr)
            if label is None:
                raise NeedsUser(
                    "softwareupdate offers no Command Line Tools package",
                    "run `xcode-select --install`, click Install, then re-run devboost",
                )
            res = ctx.ex.run(["softwareupdate", "--install", label], sudo=True)
            if not res.ok:
                raise InstallError(self.name, f"softwareupdate --install {label!r}", res.code)
            ctx.ex.run(["xcode-select", "--switch", CLT_DIR], sudo=True)
        finally:
            ctx.ex.run(["rm", "-f", CLT_PLACEHOLDER], sudo=True)


@register
class Homebrew(Module):
    name = "homebrew"
    category = "base"
    description = "Homebrew — the macOS package manager (analytics off)."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)
    requires = (XcodeClt,)

    def _present(self, ctx: Ctx) -> bool:
        res = ctx.ex.run(["brew", "--prefix"], env=BREW_ENV)
        return res.ok and res.stdout.strip() == BREW_PREFIX

    def verify(self, ctx: Ctx) -> bool:
        if not self._present(ctx):
            return False
        state = ctx.ex.run(["brew", "analytics", "state"], env=BREW_ENV)
        return state.ok and "analytics are disabled" in state.stdout.lower()

    def install(self, ctx: Ctx) -> None:
        if not self._present(ctx):
            # NONINTERACTIVE: no "press RETURN"; it uses the sudo timestamp the macOS run
            # session (cli/host.py SudoKeepalive) already holds. Never run as root.
            remote_script.run_script(
                ctx, self.name, BREW_INSTALLER, "/bin/bash", env={"NONINTERACTIVE": "1"}
            )
        res = ctx.ex.run(["brew", "analytics", "off"], env=BREW_ENV)
        if not res.ok:
            raise InstallError(self.name, "brew analytics off", res.code)


@register
class Rosetta(Module):
    name = "rosetta"
    category = "base"
    description = "Rosetta 2 — runs Intel-only apps and fast amd64 containers (macOS ≤ 27)."
    profiles = ("base",)
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True  # its install IS the macOS path (contract test)

    def verify(self, ctx: Ctx) -> bool:
        # From macOS 28 Rosetta is limited to legacy games: nothing to install; `devboost
        # doctor` lists the Intel-only apps that will stop working.
        return not rosetta_supported(ctx.os) or rosetta_present(ctx)

    def install(self, ctx: Ctx) -> None:
        if not rosetta_supported(ctx.os):
            log.warn(f"rosetta: limited on macOS {ctx.os.version_id} — see `devboost doctor`")
            return
        argv = ["softwareupdate", "--install-rosetta", "--agree-to-license"]
        res = ctx.ex.run(argv, sudo=True)
        if not res.ok:
            raise InstallError(self.name, " ".join(argv), res.code)
```

In `engine/src/devboost/cli/doctor.py`, add the check function next to `_permissions_check`:

```python
def _rosetta_check(ctx: Ctx) -> Check:
    """Informational: Rosetta state; from macOS 28 the Intel-only apps that stop working."""
    from devboost.modules import macos

    if macos.rosetta_supported(ctx.os):
        if macos.rosetta_present(ctx):
            return Check("rosetta", True, "installed")
        why = "Intel-only apps, fast amd64 containers"
        return Check("rosetta", True, f"not installed — `devboost install rosetta` ({why})")
    apps = macos.intel_only_apps(ctx)
    found = f"Intel-only apps that will not run: {', '.join(apps)}" if apps else "none found"
    return Check(
        "rosetta", True, f"macOS {ctx.os.version_id} limits Rosetta to legacy games; {found}"
    )
```

and in `run_checks`, extend the final macOS block:

```python
    if ctx.os.family == "macos":
        checks.append(_permissions_check(ctx))
        checks.append(_rosetta_check(ctx))
    return checks
```

In `profiles.toml`, put the foundation at the head of `base` (the rest of the line is unchanged; P1's `"pass","pass-store"` stay at its end):

```toml
base = ["xcode-clt","homebrew","rosetta",
        "secrets","ssh-setup","rpmfusion","dnf-tune","fedora-third-party","flatpak",
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_base.py tests/cli/test_doctor_macos.py tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS. `test_no_new_macos_gaps` is unaffected (the three modules are `families`-scoped).

- [ ] **Step 6: Commit**

```bash
git add src/devboost/exec/primitives/remote_script.py src/devboost/modules/macos.py src/devboost/cli/doctor.py ../profiles.toml tests/scripted.py tests/modules/test_macos_base.py tests/cli/test_doctor_macos.py
git commit -m "feat(macos): xcode-clt, homebrew and rosetta modules; rosetta doctor check"
```

---

### Task 4: Everything that installs through brew requires `homebrew`

Spec §1 "Ordering"; D3.

**Files:**
- Modify: `engine/src/devboost/modules/_pkgmodule.py` (`PackageModule.requires`), `engine/src/devboost/modules/apps.py` (`FlatpakApp.requires`), M2's brew-backed modules (the Task 0 Step 2 list: `ripgrep.py` `Ripgrep`, `base.py` `Chezmoi`, `mise.py` `Mise`, `editors.py` `Fresh`, `shell.py` `Starship`, `Ghostty`, `Wezterm`, `NerdFonts`, `ZshPlugins`), `engine/src/devboost/cli/app.py` (`_added_dependencies`, `_run`)
- Test: `engine/tests/core/test_homebrew_edges.py` (create)

**Interfaces:**
- Consumes: `Homebrew` (Task 3), `uses_brew` (Task 2).
- Produces: `macos_uses_brew(cls) -> bool` in the test module (the rule later tasks must satisfy: a new brew-backed module lists `Homebrew` in `requires`, directly or through a base class). `cli.app._added_dependencies(plan: list[PlannedModule], selected: Sequence[str]) -> list[str]`.

- [ ] **Step 1: Write the failing tests** — `tests/core/test_homebrew_edges.py`

```python
"""Homebrew (and so the CLT) is installed before anything that installs through brew."""

from __future__ import annotations

from pathlib import Path

from devboost.cli.app import _added_dependencies
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def macos_uses_brew(cls: type[Module]) -> bool:
    """Does this module install through Homebrew when it runs on a Mac?"""
    if cls.families and "macos" not in cls.families:
        return False
    if "macos" in cls.provided_by:
        return False
    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    if issubclass(cls, PackageModule):
        return True
    return bool(getattr(cls.per_os.macos, "uses_brew", False))


def test_brew_backed_modules_require_homebrew() -> None:
    modules = load()
    missing = sorted(
        name for name, cls in modules.items()
        if macos_uses_brew(cls) and "homebrew" not in toposort([name], modules)
    )
    assert not missing, f"add Homebrew to `requires` of: {missing}"


def test_homebrew_and_the_clt_come_first_on_a_mac(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(["ripgrep", "jq"], modules), modules, MAC,
                      gpu_marker=tmp_path / "x")
    names = [p.name for p in plan]
    assert names.index("xcode-clt") < names.index("homebrew") < names.index("ripgrep")
    assert names.index("homebrew") < names.index("jq")


def test_linux_plans_never_carry_the_macos_foundation(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(["ripgrep", "jq", "vlc"], modules), modules, FEDORA,
                      gpu_marker=tmp_path / "x")
    assert not {"homebrew", "xcode-clt"} & {p.name for p in plan}


def test_the_dependency_log_names_planned_modules_only() -> None:
    plan = [PlannedModule("flatpak"), PlannedModule("vlc")]
    assert _added_dependencies(plan, ["vlc"]) == ["flatpak"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_homebrew_edges.py -v`
Expected: FAIL: `ImportError: cannot import name '_added_dependencies'` (and, once that exists, `test_brew_backed_modules_require_homebrew` lists every PackageModule, every cask app and M2's `per_os` modules).

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/_pkgmodule.py` — add `from devboost.modules.macos import Homebrew` to the imports and, in `class PackageModule` right after `cmd: ClassVar[str]`:

```python
    #: macOS installs through brew (spec §1 "Ordering"); Linux plans drop Homebrew.
    requires: ClassVar[tuple[type[Module], ...]] = (Homebrew,)
```

`engine/src/devboost/modules/apps.py` — add `from devboost.modules.macos import Homebrew`; in `class FlatpakApp`: `requires = (Flatpak, Homebrew)`.

Each M2 brew-backed module gains `Homebrew` in `requires` (import it with `from devboost.modules.macos import Homebrew`). Where the class has no `requires` yet, add the line right after `profiles`:

```python
    requires = (Homebrew,)  # macOS installs through brew (per_os); dropped on Linux
```

That is `Ripgrep`, `Chezmoi`, `Mise`, `Fresh`, `Starship`, `Ghostty`, `Wezterm`, `NerdFonts`, and `ZshPlugins`. If one of them already has a `requires` tuple, append `Homebrew` to it. A subclass of `PackageModule` that sets its own `requires` must include `Homebrew` too; the test names it if one does.

`engine/src/devboost/cli/app.py` — add the helper above `_run`:

```python
def _added_dependencies(plan: list[PlannedModule], selected: Sequence[str]) -> list[str]:
    """Modules the plan will run that the user did not ask for (their dependencies).

    Read from the plan, not from the dependency closure: a dependency only another OS
    needs (Homebrew under a brew-backed tool on Linux) is dropped by build_plan and is
    not news to the user.
    """
    chosen = set(selected)
    return [pm.name for pm in plan if pm.name not in chosen]
```

and in `_run`, delete the two lines that compute and log `extra` from `order` before `ctx` is built, and log after the plan instead:

```python
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    plan = build_plan(order, modules, ctx.os)
    extra = _added_dependencies(plan, selected)
    if extra:
        log.info(f"+{len(extra)} required dependencies added: {', '.join(extra)}")
```

(Add `Sequence` to the `collections.abc` import if it is not there.)

- [ ] **Step 4: Run to verify pass, then fix any exact-`requires` assertions**

Run: `uv run pytest -q 2>&1 | tail -15`
Expected: `tests/core/test_homebrew_edges.py` passes. If an existing test compares a `requires` tuple exactly (find them with `grep -rn "requires ==" tests`), change it to a subset check, e.g. `assert {Flatpak} <= set(FlatpakApp.requires)`; the intent (the Linux dependency is there) is unchanged. Then `uv run mypy && uv run ruff check`.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules src/devboost/cli/app.py tests
git commit -m "feat(macos): brew-backed modules require homebrew; log only planned dependencies"
```

---

### Task 5: M4-owned modules say so on a Mac (`MacosPending`)

D1, D2. Until M4 ships the Docker runtimes and launchd timers, these modules must not run their Linux path on a Mac.

**Files:**
- Create: `engine/src/devboost/modules/_pending.py`
- Modify: `engine/src/devboost/modules/docker.py` (`Docker`, `DockerBuildCacheGc`), `engine/src/devboost/modules/dev_hygiene.py` (`AspireGc`), `engine/src/devboost/modules/system.py` (`ResticBackup`), `engine/src/devboost/modules/server.py` (`ResticB2`), `engine/src/devboost/modules/apps.py` (`ObsidianSync`), `engine/tests/core/test_macos_contract.py` (`resolvable_on_macos`)
- Test: `engine/tests/modules/test_macos_pending.py` (create)

**Interfaces:**
- Produces: `MacosPending(milestone: str, workaround: str)` — a frozen dataclass `Installer`; `verify` → `False`; `install` → `NeedsUser(f"not automated on macOS yet (lands in {milestone})", workaround)`. `resolvable_on_macos` returns `False` for a `MacosPending` `per_os.macos`. M4 replaces each entry with its real strategy and deletes the name from `KNOWN_GAPS`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_pending.py`

```python
"""M4-owned modules stop with a clear `blocked` on a Mac instead of running Linux commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module
from devboost.modules._pending import MacosPending
from devboost.modules.apps import ObsidianSync
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.docker import Docker, DockerBuildCacheGc
from devboost.modules.server import ResticB2
from devboost.modules.system import ResticBackup
from tests.core.test_macos_contract import resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PENDING: list[type[Module]] = [
    Docker, DockerBuildCacheGc, AspireGc, ResticBackup, ResticB2, ObsidianSync,
]


@pytest.mark.parametrize("cls", PENDING)
def test_m4_modules_are_pending_on_macos(cls: type[Module]) -> None:
    strategy = cls.per_os.macos
    assert isinstance(strategy, MacosPending) and strategy.milestone == "M4"
    assert strategy.workaround
    ex = FakeExecutor()
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    with pytest.raises(NeedsUser, match="lands in M4"):
        cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []  # nothing Linux-shaped ran
    assert not resolvable_on_macos(cls)  # still a known gap


def test_linux_plans_are_unchanged(tmp_path: Path) -> None:
    names = [c.name for c in PENDING]
    plan = build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {n: None for n in names}


def test_a_pending_module_blocks_what_requires_it(tmp_path: Path) -> None:
    modules = load()
    plan = build_plan(toposort(["data-services"], modules), modules, MAC,
                      gpu_marker=tmp_path / "x")
    results = {r.name: r.status for r in run_plan(plan, modules, Ctx(os=MAC, ex=FakeExecutor()))}
    assert results["docker"] == "blocked"
    assert results["data-services"] == "blocked"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_pending.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._pending'`.

- [ ] **Step 3: Implement**

Create `engine/src/devboost/modules/_pending.py`:

```python
"""A module whose macOS path is designed but owned by a later milestone.

Without this, running such a module on a Mac would execute its Linux path (systemctl,
dnf, /etc/…) and fail with a confusing error. With it, the run reports the module as
`blocked` with the milestone that brings it and a manual workaround, and the modules that
require it are blocked too. The macOS contract test counts it as a known gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import NeedsUser
from devboost.model import Ctx


@dataclass(frozen=True)
class MacosPending:
    milestone: str
    workaround: str

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser(
            f"not automated on macOS yet (lands in {self.milestone})", self.workaround
        )
```

Each of the six modules gets a `per_os` line and the M2 hand-off as the first lines of **both** `verify` and `install` (the Linux bodies are unchanged). Import `OsMap` from `devboost.core.osinfo` and `MacosPending` from `devboost.modules._pending` in each file. For `Docker`:

```python
@register
class Docker(Module):
    name = "docker"
    category = "base"
    description = "Container engine (daemon enabled; invoking user added to docker group)."
    profiles = ("base",)
    # macOS: a switchable runtime (Colima default) arrives in M4 (spec §4).
    per_os = OsMap(macos=MacosPending(
        "M4", "for now: `brew install colima docker docker-compose && colima start`"
    ))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        ...  # unchanged Linux body

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        ...  # unchanged Linux body
```

The other five, same shape, with these `per_os` lines:

```python
# DockerBuildCacheGc (docker.py)
    per_os = OsMap(macos=MacosPending(
        "M4", "set builder.gc in the runtime's docker config (Colima: `colima start --edit`)"
    ))

# AspireGc (dev_hygiene.py)
    per_os = OsMap(macos=MacosPending(
        "M4", "prune stopped Aspire containers by hand: `docker container prune`"
    ))

# ResticBackup (system.py)
    per_os = OsMap(macos=MacosPending(
        "M4", "run `restic backup --files-from ~/.config/devboost/restic-include` by hand"
    ))

# ResticB2 (server.py)
    per_os = OsMap(macos=MacosPending(
        "M4", "run the restic → B2 backup by hand; the nightly launchd timer lands in M4"
    ))

# ObsidianSync (apps.py)
    per_os = OsMap(macos=MacosPending(
        "M4", "clone the vault by hand (`git clone <repo> ~/Vault`); daily sync lands in M4"
    ))
```

In `engine/tests/core/test_macos_contract.py`, add `from devboost.modules._pending import MacosPending` to the imports and, in `resolvable_on_macos`, insert before the `if cls.per_os.macos is not None:` line:

```python
    if isinstance(cls.per_os.macos, MacosPending):
        return False  # designed, but owned by a later milestone: still a known gap
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_pending.py tests/core tests/modules/test_docker_ddev.py tests/modules/test_apps.py tests/modules/test_system.py tests/modules/test_server.py -v && uv run mypy && uv run ruff check`
Expected: PASS. The six names stay in `KNOWN_GAPS` (`test_known_gaps_are_still_gaps` passes because pending ≠ resolved).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_pending.py src/devboost/modules/docker.py src/devboost/modules/dev_hygiene.py src/devboost/modules/system.py src/devboost/modules/server.py src/devboost/modules/apps.py tests/core/test_macos_contract.py tests/modules/test_macos_pending.py
git commit -m "feat(macos): M4-owned modules report blocked on a Mac instead of running Linux steps"
```

---

### Task 6: Linux-only modules and what macOS already provides

D22. Spec §2 "`provided_by=("macos",)`" and "`families` = Linux only".

**Files:**
- Modify: `engine/src/devboost/core/osinfo.py` (`LINUX_FAMILIES`), `engine/src/devboost/modules/server.py` (`AgentSudo`, `Zram`), `engine/src/devboost/modules/browser_view.py`, `engine/src/devboost/modules/caddy.py`, `engine/src/devboost/modules/code_server.py`, `engine/src/devboost/modules/crossarch_build.py`, `engine/src/devboost/modules/system.py` (`Earlyoom`, `GpuDetect`, `Fwupd`, `Thermald`, `PowerProfilesDaemon`), `engine/src/devboost/modules/apps.py` (`Gearlever`, `Flameshot`), `engine/src/devboost/modules/multimedia.py` (`VaHwaccel`), `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_macos_sweep.py` (create)

**Interfaces:**
- Produces: `core.osinfo.LINUX_FAMILIES: tuple[str, ...] = ("fedora", "debian", "arch")` (if Task 0 found an equivalent M2 constant, use that name everywhere below instead and skip adding this one).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_sweep.py`

```python
"""Linux-only modules leave the Mac plan; what macOS already has is reported as provided."""

from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import LINUX_FAMILIES, OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))

LINUX_ONLY = [
    "agent-sudo", "browser-view", "caddy", "code-server", "crossarch-build",
    "earlyoom", "gpu-detect", "zram", "gearlever",
]
PROVIDED = ["flameshot", "fwupd", "thermald", "power-profiles-daemon", "va-hwaccel"]


def test_linux_only_modules_leave_the_mac_plan(tmp_path: Path) -> None:
    modules = load()
    for name in LINUX_ONLY:
        assert modules[name].families == LINUX_FAMILIES, name
    assert build_plan(LINUX_ONLY, modules, MAC, gpu_marker=tmp_path / "x") == []


def test_macos_already_provides_these(tmp_path: Path) -> None:
    plan = build_plan(PROVIDED, load(), MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {n: "provided-by-macos" for n in PROVIDED}


def test_linux_plans_keep_them(tmp_path: Path) -> None:
    plan = build_plan(LINUX_ONLY + PROVIDED, load(), FEDORA, gpu_marker=tmp_path / "x")
    assert {p.name for p in plan} == set(LINUX_ONLY + PROVIDED)
    assert all(p.skip_reason is None for p in plan)


def test_omarchy_still_provides_its_own(tmp_path: Path) -> None:
    plan = build_plan(["flameshot", "thermald"], load(), OMARCHY, gpu_marker=tmp_path / "x")
    assert {p.skip_reason for p in plan} == {"provided-by-omarchy"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_sweep.py -v`
Expected: FAIL with `ImportError: cannot import name 'LINUX_FAMILIES'`.

- [ ] **Step 3: Implement**

`engine/src/devboost/core/osinfo.py`, after the `_FAMILY` table:

```python
#: Every Linux family dev-boost supports. A module that cannot exist on a Mac declares
#: ``families = LINUX_FAMILIES`` so macOS plans drop it (spec §2 "families = Linux only").
LINUX_FAMILIES: tuple[str, ...] = ("fedora", "debian", "arch")
```

Add to each Linux-only class (import `LINUX_FAMILIES` from `devboost.core.osinfo`; `ClassVar` from `typing` where the file lacks it), right after `profiles`:

```python
    families: ClassVar[tuple[str, ...]] = LINUX_FAMILIES  # <reason>
```

with these reasons: `AgentSudo` "passwordless sudo for agents on a server/brain"; `BrowserView`, `Caddy`, `CodeServer`, `CrossArchBuild` "brain-host service (a Mac is never a brain, spec: out of scope)"; `Earlyoom` "Linux OOM killer"; `GpuDetect` "picks a Linux GPU driver (lspci)"; `Zram` "Linux compressed swap"; `Gearlever` "AppImage manager".

Set `provided_by` (keep existing entries):

```python
# Flameshot (apps.py)       — ⌘⇧5 is built in; the brew cask is deprecated
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy", "macos")
# Fwupd (system.py)         — macOS updates firmware through Software Update
    provided_by: ClassVar[tuple[str, ...]] = ("macos",)
# Thermald (system.py)      — thermal management is the OS's job on a Mac
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy", "macos")
# PowerProfilesDaemon       — Low Power Mode in System Settings
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy", "macos")
# VaHwaccel (multimedia.py) — VideoToolbox is built in
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy", "macos")
```

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"agent-sudo"`, `"browser-view"`, `"caddy"`, `"code-server"`, `"crossarch-build"`, `"earlyoom"`, `"flameshot"`, `"fwupd"`, `"gearlever"`, `"gpu-detect"`, `"power-profiles-daemon"`, `"thermald"`, `"va-hwaccel"`, `"zram"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS; `test_known_gaps_are_still_gaps` confirms the fourteen names are resolved.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/core/osinfo.py src/devboost/modules tests/core/test_macos_contract.py tests/modules/test_macos_sweep.py
git commit -m "feat(macos): Linux-only modules leave Mac plans; macOS-provided ones are skipped"
```

---

### Task 7: Formulae and casks — GUI apps, editors, mosh, uv, smartmontools, build-tools, ffmpeg

Spec §2 "Formulae" and "Casks"; D24, D26.

**Files:**
- Modify: `engine/src/devboost/modules/apps.py` (casks), `engine/src/devboost/modules/editors.py` (`Vscode`), `engine/src/devboost/modules/optional.py` (`Neovim`, `JetbrainsToolbox`), `engine/src/devboost/modules/mosh.py`, `engine/src/devboost/modules/dev_stacks.py` (`Uv`), `engine/src/devboost/modules/system.py` (`SystemService`, `Smartmontools`), `engine/src/devboost/modules/base.py` (`BuildTools`), `engine/src/devboost/modules/multimedia.py` (`FfmpegFull`), `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_macos_formulae_casks.py` (create)

**Interfaces:**
- Consumes: `BrewFormula`, `BrewCask`, `os_strategy` (M2); `Homebrew`, `XcodeClt` (Task 3).
- Produces: `cask` on `Obsidian`/`Bruno`/`Bitwarden`/`Localsend`/`Vlc`; `per_os.macos` = `BrewCask("visual-studio-code")` (vscode), `BrewCask("jetbrains-toolbox")`, `BrewFormula("neovim")`, `BrewFormula("mosh")`, `BrewFormula("uv")`, `BrewFormula("smartmontools")`, `BrewFormula("cmake")` (build-tools, which also requires `XcodeClt`), `BrewFormula("ffmpeg")` (ffmpeg-full, now `families = ("fedora", "macos")`). `SystemService.verify`/`install` hand off to `os_strategy` first.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_formulae_casks.py`

```python
"""Plain Homebrew formulae and casks for the catalog (spec §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules.apps import Bitwarden, Bruno, FlatpakApp, Localsend, Obsidian, Vlc
from devboost.modules.base import BuildTools
from devboost.modules.dev_stacks import Uv
from devboost.modules.editors import Vscode
from devboost.modules.macos import XcodeClt
from devboost.modules.mosh import Mosh
from devboost.modules.multimedia import FfmpegFull
from devboost.modules.optional import JetbrainsToolbox, Neovim
from devboost.modules.system import Smartmontools

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

CASK_APPS: list[tuple[type[FlatpakApp], str]] = [
    (Obsidian, "obsidian"), (Bruno, "bruno"), (Bitwarden, "bitwarden"),
    (Localsend, "localsend"), (Vlc, "vlc"),
]
STRATEGIES: list[tuple[type[Module], Installer]] = [
    (Vscode, BrewCask("visual-studio-code")),
    (JetbrainsToolbox, BrewCask("jetbrains-toolbox")),
    (Neovim, BrewFormula("neovim")),
    (Mosh, BrewFormula("mosh")),
    (Uv, BrewFormula("uv")),
    (Smartmontools, BrewFormula("smartmontools")),
    (BuildTools, BrewFormula("cmake")),
    (FfmpegFull, BrewFormula("ffmpeg")),
]


@pytest.mark.parametrize(("cls", "cask"), CASK_APPS)
def test_gui_apps_install_their_cask(cls: type[FlatpakApp], cask: str) -> None:
    assert cls.cask == cask
    ex = FakeExecutor(scripts={"brew": Result(1)})  # not installed yet
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["brew", "install", "--cask", "-y", "--adopt", cask]


@pytest.mark.parametrize(("cls", "strategy"), STRATEGIES)
def test_macos_goes_through_its_brew_strategy(cls: type[Module], strategy: Installer) -> None:
    assert cls.per_os.macos == strategy
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls[0][:2] == ["brew", "list"]  # brew decides, not `which`
    ex = FakeExecutor(scripts={"brew": Result(1)})
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1][:2] == ["brew", "install"]


def test_linux_paths_are_unchanged() -> None:
    ex = FakeExecutor()
    Mosh().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == [["sudo", "dnf", "install", "-y", "mosh"]]
    ex = FakeExecutor()
    Smartmontools().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "install", "-y", "smartmontools"] in ex.calls
    ex = FakeExecutor()
    FfmpegFull().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls[0][:3] == ["sudo", "dnf", "swap"]


def test_build_tools_needs_the_command_line_tools(tmp_path: Path) -> None:
    assert XcodeClt in BuildTools.requires
    plan = build_plan(["ffmpeg-full", "build-tools"], load(), MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {"ffmpeg-full": None, "build-tools": None}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_formulae_casks.py -v`
Expected: FAIL (`assert None == 'obsidian'`, `assert OsMap(...).macos is None`, …).

- [ ] **Step 3: Implement**

`apps.py` — one line per app class:

```python
# class Obsidian:   cask = "obsidian"
# class Bruno:      cask = "bruno"
# class Bitwarden:  cask = "bitwarden"
# class Localsend:  cask = "localsend"
# class Vlc:        cask = "vlc"
```

Every other class below gets the same three-part change: a `per_os` line, `Homebrew` in `requires` (`from devboost.modules.macos import Homebrew`), and the M2 hand-off as the first lines of `verify` and `install`. Import `OsMap` from `devboost.core.osinfo` and `BrewFormula`/`BrewCask` from `devboost.modules._brew` where the file lacks them. `Mosh` in full:

```python
@register
class Mosh(Module):
    name = "mosh"
    category = "remote"
    description = "Mosh — roaming-resilient terminal transport (client + mosh-server)."
    profiles = ("cli", "remote", "brain-host")
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewFormula("mosh"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("mosh")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # One package ships both the `mosh` client and `mosh-server`. …(existing comment)
        pkg.install(ctx, "mosh")
```

The others (Linux bodies unchanged):

```python
# Vscode (editors.py)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewCask("visual-studio-code"))

# JetbrainsToolbox (optional.py)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewCask("jetbrains-toolbox"))

# Neovim (optional.py)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewFormula("neovim"))

# Uv (dev_stacks.py)
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewFormula("uv"))

# BuildTools (base.py) — the CLT bring clang/make/git; brew adds the one missing build tool
    requires = (XcodeClt, Homebrew)
    per_os = OsMap(macos=BrewFormula("cmake"))

# FfmpegFull (multimedia.py) — Homebrew's ffmpeg is already the full build
    requires = (Rpmfusion, Homebrew)
    families: ClassVar[tuple[str, ...]] = ("fedora", "macos")
    per_os = OsMap(macos=BrewFormula("ffmpeg"))
```

`FfmpegFull`'s hand-off goes **before** its `if ctx.os.family != "fedora":` guards. Its description becomes `"Full ffmpeg: RPM Fusion's on Fedora (swaps ffmpeg-free), Homebrew's on macOS."`.

`system.py` — `SystemService` hands off, so `Smartmontools` only declares data:

```python
class SystemService(Module):
    """Install a package and enable its system service (verify = is-enabled)."""

    svc_pkg: ClassVar[str]
    service: ClassVar[str]
    category = "system"
    profiles = ("system",)

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return systemd.is_enabled(ctx, self.service)

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        pkg.install(ctx, self.svc_pkg)
        systemd.enable_system_unit(ctx, self.service, now=True)


@register
class Smartmontools(SystemService):
    name = "smartmontools"
    description = "Disk SMART monitoring."
    svc_pkg = "smartmontools"
    service = "smartd"
    requires = (Homebrew,)
    # macOS: the smartctl tool only — no smartd service (launchd would be M4's business).
    per_os = OsMap(macos=BrewFormula("smartmontools"))
```

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"bitwarden"`, `"bruno"`, `"build-tools"`, `"jetbrains-toolbox"`, `"localsend"`, `"mosh"`, `"neovim"`, `"obsidian"`, `"smartmontools"`, `"uv"`, `"vlc"`, `"vscode"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS (including `test_brew_backed_modules_require_homebrew` from Task 4 and every Fedora/Ubuntu/Arch test of these modules).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules tests/core/test_macos_contract.py tests/modules/test_macos_formulae_casks.py
git commit -m "feat(macos): casks for the GUI apps; brew formulae for mosh, uv, neovim, cmake, smartmontools, ffmpeg"
```

---

### Task 8: herdr pinned per OS and arch, `herdr-plugins` and `glow` by default

Spec §2 ("herdr pins", `cli` += `herdr-plugins`, `glow`), §3 (herdr image paste); carry-over M3 item 2; D8–D11.

**Files:**
- Modify: `catalog.toml` (`[herdr]`), `engine/src/devboost/media/catalog.py`, `engine/src/devboost/modules/herdr.py`, `engine/src/devboost/modules/cli_tools.py` (new `Glow`), `dotfiles/dot_config/herdr/config.toml`, `profiles.toml` (`cli`), `engine/tests/media/test_catalog.py`, `engine/tests/modules/test_herdr.py`, `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_herdr_macos.py`, `engine/tests/modules/test_glow.py` (create)

**Interfaces:**
- Produces:
  - `media.catalog.asset_key(os_info: OsInfo) -> str` → `"macos-<arch>"` on macOS, `"linux-<arch>"` elsewhere. Every pinned-asset module uses it.
  - `[herdr]` pin 0.9.1 with keys `linux-x86_64`, `linux-aarch64`, `macos-aarch64`; `herdr_pin()` rejects any other key shape (`MediaError`).
  - `Herdr.portable = True`; `Herdr.verify` also requires `herdr --version` ≥ the pin.
  - `HerdrPlugins.profiles == ("cli", "optional-agents", "brain-tools")`, `portable = True`.
  - `Glow(PackageModule)`: `name = "glow"`, `profiles = ("cli",)`; Debian via Charm's apt repo.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_herdr_macos.py`:

```python
"""herdr on every OS: one pin keyed by (os, arch), BSD-safe install, image paste kept."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, MediaError
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import load_profiles
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.catalog import asset_key, herdr_pin
from devboost.model import Ctx
from devboost.modules.herdr import Herdr, HerdrPlugins
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "aarch64", id_like=("arch",))
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_asset_key_names_the_os_and_the_arch() -> None:
    assert asset_key(MAC) == "macos-aarch64"
    assert asset_key(FEDORA) == "linux-x86_64"
    assert asset_key(OMARCHY) == "linux-aarch64"


def test_live_pin_is_keyed_by_os_and_arch() -> None:
    pin = herdr_pin()
    assert pin.version == "0.9.1"
    assert set(pin.assets) == {"linux-x86_64", "linux-aarch64", "macos-aarch64"}
    for key, asset in pin.assets.items():
        assert asset.url == (
            f"https://github.com/herdrdev/herdr/releases/download/v0.9.1/herdr-{key}"
        )


def test_catalog_rejects_arch_only_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(
        '[herdr]\nversion = "0.9.1"\n[herdr.assets.aarch64]\n'
        f'url = "https://x/herdr"\nsha256 = "{"a" * 64}"\n',
        encoding="utf-8",
    )

    class _FakeSettings:
        catalog_path = p

    monkeypatch.setattr("devboost.media.catalog.settings", _FakeSettings())
    herdr_pin.cache_clear()
    try:
        with pytest.raises(MediaError, match="asset keys must be"):
            herdr_pin()
    finally:
        herdr_pin.cache_clear()


def test_mac_installs_the_macos_binary_bsd_safely(tmp_path: Path) -> None:
    ex = FakeExecutor()
    Herdr().install(Ctx(os=MAC, ex=ex))
    script = ex.calls[0][2]
    assert "herdr-macos-aarch64" in script and "herdr-linux" not in script
    assert "shasum -a 256 -c -" in script and "sha256sum" not in script
    assert f'mkdir -p "{tmp_path}/.local/bin"' in script
    assert f'install -m 755 "$tmp/herdr" "{tmp_path}/.local/bin/herdr"' in script
    assert "install -D" not in script


def test_linux_keeps_sha256sum() -> None:
    ex = FakeExecutor()
    Herdr().install(Ctx(os=FEDORA, ex=ex))
    script = ex.calls[0][2]
    assert "herdr-linux-x86_64" in script and "sha256sum -c -" in script


def test_an_intel_mac_never_gets_a_linux_binary() -> None:
    with pytest.raises(InstallError, match="macos-x86_64"):
        Herdr().install(Ctx(os=OsInfo("macos", "macos", "x86_64"), ex=FakeExecutor()))


@pytest.mark.parametrize(
    ("installed", "ok"), [("herdr 0.7.5", False), ("herdr 0.9.1", True), ("herdr 0.10.0", True)]
)
def test_verify_upgrades_an_older_herdr_and_keeps_a_newer_one(installed: str, ok: bool) -> None:
    ex = Scripted(present={"herdr"},
                  answers={("herdr", "--version"): Result(0, stdout=installed + "\n")})
    assert Herdr().verify(Ctx(os=FEDORA, ex=ex)) is ok


def test_herdr_config_keeps_ctrl_v_for_remote_image_paste() -> None:
    cfg = REPO_ROOT / "dotfiles" / "dot_config" / "herdr" / "config.toml"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["keys"]["remote_image_paste"] == "ctrl+v"


def test_plugins_and_glow_are_in_cli_on_every_os() -> None:
    cli = load_profiles(REPO_ROOT / "profiles.toml")["cli"]
    assert "herdr-plugins" in cli and "glow" in cli
    assert "cli" in HerdrPlugins.profiles
    assert Herdr.portable and HerdrPlugins.portable
```

`tests/modules/test_glow.py`:

```python
"""glow on every OS: Homebrew, dnf, pacman, and Charm's apt repo on Debian/Ubuntu."""

from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.cli_tools import Glow

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04")
ARCH = OsInfo("arch", "arch", "x86_64")


def test_glow_on_macos_fedora_and_arch() -> None:
    for os_info, call in (
        (MAC, ["brew", "install", "--formula", "-y", "glow"]),
        (FEDORA, ["sudo", "dnf", "install", "-y", "glow"]),
        (ARCH, ["sudo", "pacman", "-S", "--needed", "--noconfirm", "glow"]),
    ):
        ex = FakeExecutor()
        Glow().install(Ctx(os=os_info, ex=ex))
        assert ex.calls[-1] == call, os_info.distro


def test_glow_on_ubuntu_comes_from_charms_apt_repo() -> None:
    ex = FakeExecutor()
    Glow().install(Ctx(os=UBUNTU, ex=ex))
    keyring = next(c for c in ex.calls if c[:2] == ["sudo", "sh"])
    assert "https://repo.charm.sh/apt/gpg.key" in keyring[-1]
    assert "/etc/apt/keyrings/repo-charm-sh.gpg" in keyring[-1]
    assert ["sudo", "tee", "/etc/apt/sources.list.d/repo-charm-sh.list"] in ex.calls
    assert ex.calls[-1] == ["sudo", "apt-get", "install", "-y", "glow"]


def test_glow_is_a_self_updating_cli_tool() -> None:
    assert Glow.profiles == ("cli",) and Glow.self_updating is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_herdr_macos.py tests/modules/test_glow.py -v`
Expected: FAIL with `ImportError: cannot import name 'asset_key'` / `'Glow'`.

- [ ] **Step 3: Implement**

`catalog.toml` — replace the whole `[herdr]` block (digests are the `sha256:` digests GitHub publishes for the v0.9.1 assets, read 2026-09-19 with `gh api repos/herdrdev/herdr/releases/tags/v0.9.1`; re-read them at execution time and stop if they differ):

```toml
# herdr — assets keyed "<os>-<arch>" (media.catalog.asset_key): a Mac never gets a Linux
# binary and there is no fallback between keys. The repo moved to herdrdev/herdr.
[herdr]
version = "0.9.1"

[herdr.assets.linux-x86_64]
url = "https://github.com/herdrdev/herdr/releases/download/v0.9.1/herdr-linux-x86_64"
sha256 = "2a02fed16beb651ef006e1d43f048f652ca4dc58ad053cd2d44450563d5c54b7"

[herdr.assets.linux-aarch64]
url = "https://github.com/herdrdev/herdr/releases/download/v0.9.1/herdr-linux-aarch64"
sha256 = "f4ccf4de745f2cb9a39a983e9ba3703dad50ec2a58dea83026ceab721bbd8d9e"

[herdr.assets.macos-aarch64]
url = "https://github.com/herdrdev/herdr/releases/download/v0.9.1/herdr-macos-aarch64"
sha256 = "5fc7a7e7adfaca56fa80aa89dcb025693357268dab8285b9ce2d08a2313c89de"
```

`engine/src/devboost/media/catalog.py` — add `import re`, `field_validator` to the pydantic import, `from devboost.core.osinfo import OsInfo`; change the `HerdrSpec.assets` comment to `# "<os>-<arch>" (see asset_key) -> asset`; add after `HerdrSpec`:

```python
_ASSET_KEY = re.compile(r"^(linux|macos)-(x86_64|aarch64)$")


def asset_key(os_info: OsInfo) -> str:
    """The catalog key of a pinned binary for this host: ``<os>-<arch>``.

    Keyed by OS *and* arch (never arch alone), so a Mac can never pick a Linux binary.
    """
    return f"{'macos' if os_info.family == 'macos' else 'linux'}-{os_info.arch}"
```

and give `_HerdrRow` a validator:

```python
class _HerdrRow(BaseModel):
    version: str
    assets: dict[str, _HerdrAssetRow] = Field(min_length=1)

    @field_validator("assets")
    @classmethod
    def _os_arch_keys(cls, v: dict[str, _HerdrAssetRow]) -> dict[str, _HerdrAssetRow]:
        bad = sorted(k for k in v if not _ASSET_KEY.match(k))
        if bad:
            raise ValueError(f"asset keys must be <linux|macos>-<arch>, got {bad}")
        return v
```

`engine/src/devboost/modules/herdr.py` — add `import re` and `from devboost.media.catalog import asset_key, herdr_pin`; replace `Herdr`'s class attributes after `provided_by`, `verify`, and `install`:

```python
    #: Same install code on every OS: the catalog pin is keyed by (os, arch).
    portable: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("herdr"):
            return False
        # An older pin is upgraded; a newer herdr (after `herdr update`) is kept as is.
        have = _version(ctx.ex.run(["herdr", "--version"]).stdout)
        want = _version(herdr_pin().version)
        return have is None or want is None or have >= want

    def install(self, ctx: Ctx) -> None:
        pin = herdr_pin()
        key = asset_key(ctx.os)
        asset = pin.assets.get(key)
        if asset is None:
            raise InstallError("herdr", f"no pinned binary for {key!r}", 1)
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        # BSD-safe on macOS: shasum ships with every Mac, and BSD `install` has no -D.
        check = "shasum -a 256 -c -" if ctx.os.family == "macos" else "sha256sum -c -"
        # Download → verify SHA256 (the check fails the `set -e` script on a mismatch,
        # before install) → install onto PATH. No native package is used (see D9).
        script = (
            "set -e\n"
            "tmp=$(mktemp -d)\n"
            f'curl -fL --retry 2 -o "$tmp/herdr" "{asset.url}"\n'
            f'echo "{asset.sha256}  $tmp/herdr" | {check}\n'
            f'mkdir -p "{bindir}"\n'
            f'install -m 755 "$tmp/herdr" "{bindir}/herdr"\n'
            'rm -rf "$tmp"\n'
        )
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise InstallError("herdr", "download or checksum verification failed", res.code)
```

with this helper above the class:

```python
def _version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None
```

In `HerdrPlugins`: `profiles = ("cli", "optional-agents", "brain-tools")` and add `portable: ClassVar[bool] = True  # only calls the herdr CLI`.

`engine/src/devboost/modules/cli_tools.py` — add `from devboost.core.osinfo import OsMap` and `AptRepo` to the `devboost.model` import, then after `Direnv`:

```python
# Charm's own apt repo (glow README): Ubuntu 24.04 has no glow and 26.04 ships 2.x.
_CHARM_APT = AptRepo(
    list_line=(
        "deb [signed-by=/etc/apt/keyrings/repo-charm-sh.gpg] https://repo.charm.sh/apt/ * *"
    ),
    key_url="https://repo.charm.sh/apt/gpg.key",
)


@register
class Glow(PackageModule):
    name = "glow"
    category = "cli"
    description = "Render Markdown in the terminal (READMEs, plans; herdr-file-viewer uses it)."
    profiles = ("cli",)
    cmd = "glow"
    fedora_pkg = "glow"

    def install_linux(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, "glow", source=OsMap(debian=_CHARM_APT))
            return
        super().install_linux(ctx)
```

(`Apt.add_repo` names the keyring and list after the first URL's host, `repo-charm-sh`, which is why the `signed-by` path uses that name.)

`dotfiles/dot_config/herdr/config.toml` — in `[keys]`, after `focus_pane_left`:

```toml
# herdr --remote pastes a local clipboard image into the remote pane on Ctrl+V (herdr's
# default since 0.7.1, pinned here on purpose): no terminal config binds Ctrl+V.
remote_image_paste = "ctrl+v"
```

`profiles.toml` — `cli` gains `"herdr-plugins","glow"` at its end.

`engine/tests/media/test_catalog.py::test_herdr_pin_is_present_in_live_catalog` — replace the key and URL assertions:

```python
    assert {"linux-x86_64", "linux-aarch64", "macos-aarch64"} <= set(pin.assets)
    for asset in pin.assets.values():
        assert asset.url.startswith("https://github.com/herdrdev/herdr/")
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
```

`engine/tests/modules/test_herdr.py::test_herdr_plugins_requires_herdr` — the profile assertion becomes `assert HerdrPlugins.profiles == ("cli", "optional-agents", "brain-tools")`.

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"herdr"`, `"herdr-plugins"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_herdr.py tests/modules/test_herdr_macos.py tests/modules/test_glow.py tests/media/test_catalog.py tests/core tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS. `test_herdr_install_selects_aarch64` still finds `herdr-linux-aarch64`; `test_herdr_install_raises_on_unknown_arch` matches `riscv64` in `'linux-riscv64'`.

- [ ] **Step 5: Commit**

```bash
git add ../catalog.toml ../profiles.toml ../dotfiles/dot_config/herdr/config.toml src/devboost/media/catalog.py src/devboost/modules/herdr.py src/devboost/modules/cli_tools.py tests/media/test_catalog.py tests/modules/test_herdr.py tests/modules/test_herdr_macos.py tests/modules/test_glow.py tests/core/test_macos_contract.py
git commit -m "feat(herdr): 0.9.1 pinned per OS and arch, macOS binary; herdr-plugins and glow in cli"
```

---

### Task 9: .NET SDK and Android SDK on macOS

Spec §2 per-OS rows `dotnet-sdk`, `android-sdk`; D12, D13.

**Files:**
- Modify: `engine/src/devboost/modules/dev_stacks.py` (`DotnetSdk`, `AndroidSdk`), `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_dotnet_android_macos.py` (create)

**Interfaces:**
- Consumes: `remote_script.run_script` (Task 3), `userpaths.dotnet_root` (Task 1), `BrewCask` (M2/Task 2), `Homebrew` (Task 3).
- Produces: `DotnetSdk.per_os.macos == _DotnetUserInstall()` (not brew); `AndroidSdk.per_os.macos == _AndroidSdkMac()` (`uses_brew = True`), `AndroidSdk.requires == (Mise, Homebrew)`. Module constant `_ANDROID_PACKAGES` shared by both OSes.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_dotnet_android_macos.py`

```python
"""The .NET SDK in ~/.dotnet and the Android SDK in ~/Library/Android/sdk on macOS."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.dev_stacks import AndroidSdk, DotnetSdk
from devboost.modules.macos import Homebrew
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PACKAGES = "'platform-tools' 'platforms;android-35' 'build-tools;35.0.0'"


def test_dotnet_on_macos_runs_the_official_script_into_home(tmp_path: Path) -> None:
    ex = Scripted(answers={("mktemp", "-d"): Result(0, stdout="/tmp/dn\n")})
    DotnetSdk().install(Ctx(os=MAC, ex=ex))
    assert ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o", "/tmp/dn/install.sh",
            "https://dot.net/v1/dotnet-install.sh"] in ex.calls
    assert ["bash", "/tmp/dn/install.sh", "--channel", "10.0",
            "--install-dir", str(tmp_path / ".dotnet")] in ex.calls
    assert not any(c[0] == "sudo" for c in ex.calls)


@pytest.mark.parametrize(
    ("listing", "ok"), [("10.0.104 [/x/sdk]\n", True), ("9.0.300 [/x/sdk]\n", False)]
)
def test_dotnet_verify_reads_the_user_sdk(tmp_path: Path, listing: str, ok: bool) -> None:
    dotnet = str(tmp_path / ".dotnet" / "dotnet")
    ex = Scripted(answers={(dotnet, "--list-sdks"): Result(0, stdout=listing)})
    assert DotnetSdk().verify(Ctx(os=MAC, ex=ex)) is ok
    missing = Scripted(answers={(dotnet,): Result(127)})
    assert DotnetSdk().verify(Ctx(os=MAC, ex=missing)) is False


def test_dotnet_on_fedora_is_unchanged() -> None:
    ex = FakeExecutor()
    DotnetSdk().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "install", "-y", "dotnet-sdk-10.0"] in ex.calls


def test_android_on_macos_uses_the_cmdline_tools_cask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    ex = Scripted(answers={("brew", "list"): Result(1)})
    AndroidSdk().install(Ctx(os=MAC, ex=ex))
    sdk = tmp_path / "Library" / "Android" / "sdk"
    assert ex.calls[0] == ["mise", "use", "-g", "java@temurin-17"]
    assert ["brew", "install", "--cask", "-y", "--adopt", "android-commandlinetools"] in ex.calls
    assert ex.calls[-1] == ["sh", "-c", f"yes | sdkmanager --sdk_root={sdk} {PACKAGES}"]
    assert not any("profile.d" in " ".join(c) for c in ex.calls)
    assert sdk.is_dir()


def test_android_follows_android_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = tmp_path / "custom-sdk"
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    assert AndroidSdk().verify(Ctx(os=MAC, ex=FakeExecutor())) is False
    (sdk / "platform-tools").mkdir(parents=True)
    (sdk / "platform-tools" / "adb").write_text("", encoding="utf-8")
    assert AndroidSdk().verify(Ctx(os=MAC, ex=FakeExecutor())) is True


def test_android_requires_homebrew_on_a_mac() -> None:
    assert Homebrew in AndroidSdk.requires
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_dotnet_android_macos.py -v`
Expected: FAIL (the macOS runs take the Linux path: `dnf install` / `/etc/profile.d`).

- [ ] **Step 3: Implement** in `engine/src/devboost/modules/dev_stacks.py`

Add imports: `import shlex`, `from dataclasses import dataclass`, `from typing import ClassVar`, `from devboost.core.errors import InstallError`, `from devboost.core.osinfo import OsMap`, `from devboost.exec import userpaths`, `from devboost.exec.primitives import remote_script` (extend the existing `mise, pkg` import), `from devboost.modules._brew import BrewCask`, `from devboost.modules.macos import Homebrew`.

Above `class DotnetSdk`:

```python
_DOTNET_INSTALL = "https://dot.net/v1/dotnet-install.sh"
_DOTNET_CHANNEL = "10.0"  # .NET 10 LTS, the same pin as the Linux packages


def _has_sdk(listing: str) -> bool:
    major = _DOTNET_CHANNEL.split(".", 1)[0] + "."
    return any(ln.startswith(major) for ln in listing.splitlines())


@dataclass(frozen=True)
class _DotnetUserInstall:
    """macOS: Microsoft's dotnet-install.sh into ~/.dotnet — no sudo, no .pkg (spec §2).

    The executor puts ~/.dotnet on PATH (dotnet tools install in the same run); env.sh
    exports DOTNET_ROOT so tools like csharp-ls find the runtime later.
    """

    def verify(self, ctx: Ctx) -> bool:
        dotnet = userpaths.dotnet_root(_home()) / "dotnet"
        out = ctx.ex.run([str(dotnet), "--list-sdks"])
        return out.ok and _has_sdk(out.stdout)

    def install(self, ctx: Ctx) -> None:
        remote_script.run_script(
            ctx, "dotnet-sdk", _DOTNET_INSTALL, "bash",
            "--channel", _DOTNET_CHANNEL, "--install-dir", str(userpaths.dotnet_root(_home())),
        )
```

`DotnetSdk` gets `per_os = OsMap(macos=_DotnetUserInstall())`, the hand-off at the top of `verify` and `install`, and its Linux verify uses the shared check:

```python
    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        out = ctx.ex.run(["dotnet", "--list-sdks"])
        return out.ok and _has_sdk(out.stdout)
```

Above `class AndroidSdk`:

```python
_ANDROID_PACKAGES = "'platform-tools' 'platforms;android-35' 'build-tools;35.0.0'"


@dataclass(frozen=True)
class _AndroidSdkMac:
    """macOS: Google's command-line tools from the Homebrew cask (sdkmanager lands in
    /opt/homebrew/bin), the SDK in $ANDROID_HOME (~/Library/Android/sdk, exported by
    env.sh). No /etc/profile.d on a Mac."""

    uses_brew: ClassVar[bool] = True

    @staticmethod
    def sdk() -> Path:
        default = _home() / "Library" / "Android" / "sdk"
        return Path(os.environ.get("ANDROID_HOME") or str(default))

    def verify(self, ctx: Ctx) -> bool:
        return (self.sdk() / "platform-tools" / "adb").exists()

    def install(self, ctx: Ctx) -> None:
        mise.use_global(ctx, "java@temurin-17")
        BrewCask("android-commandlinetools").install(ctx)
        sdk = self.sdk()
        sdk.mkdir(parents=True, exist_ok=True)
        cmd = f"yes | sdkmanager --sdk_root={shlex.quote(str(sdk))} {_ANDROID_PACKAGES}"
        res = ctx.ex.run(["sh", "-c", cmd])
        if not res.ok:
            raise InstallError("android-sdk", f"sdkmanager {_ANDROID_PACKAGES}", res.code)
```

`AndroidSdk`: `requires = (Mise, Homebrew)`, `per_os = OsMap(macos=_AndroidSdkMac())`, the hand-off at the top of `verify` and `install`, and its Linux `sdkmanager` line uses the constant (same string as before):

```python
        ctx.ex.run(["sh", "-c", f"yes | {sm} --sdk_root={sdk} {_ANDROID_PACKAGES}"])
```

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"android-sdk"`, `"dotnet-sdk"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_dotnet_android_macos.py tests/modules/test_dev_stacks.py tests/modules/test_ubuntu_dev_stacks.py tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/dev_stacks.py tests/modules/test_dotnet_android_macos.py tests/core/test_macos_contract.py
git commit -m "feat(macos): .NET SDK via dotnet-install.sh in ~/.dotnet; Android SDK via the cmdline-tools cask"
```

---

### Task 10: ddev, Tailscale and Playwright on macOS

Spec §2 per-OS rows `ddev`, `tailscale`, `playwright`; §1 "Errors"; D14, D15, D27.

**Files:**
- Modify: `engine/src/devboost/modules/ddev.py` (`Ddev`, `DdevRemote`), `engine/src/devboost/modules/server.py` (`Tailscale`), `engine/src/devboost/modules/dev_stacks.py` (`Playwright`), `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_ddev_tailscale_macos.py` (create)

**Interfaces:**
- Consumes: `pkg.install(..., source=OsMap(macos=BrewTap(...)))` (M1), `BrewCask` (Task 2), `_credentials.is_interactive` (M1), `server._secret` (existing), `Homebrew` (Task 3).
- Produces: `Ddev.per_os.macos == _DdevMac()` and `Tailscale.per_os.macos == _TailscaleMac()` (both `uses_brew = True`, both require `Homebrew`); `DdevRemote.portable`, `Playwright.portable`; `server.ts_cli() -> Path` (`~/.local/bin/tailscale`).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_ddev_tailscale_macos.py`

```python
"""ddev (tap + mkcert), Tailscale (app + CLI + approval) and Playwright on macOS."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import server
from devboost.modules.ddev import Ddev, DdevRemote
from devboost.modules.dev_stacks import Playwright
from devboost.modules.server import Tailscale
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
APP_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def _no_brew_formulae(caroot: Path) -> Scripted:
    return Scripted(answers={
        ("brew", "list"): Result(1),
        ("mkcert", "-CAROOT"): Result(0, stdout=f"{caroot}\n"),
    })


def test_ddev_taps_installs_and_trusts_the_ca_when_someone_is_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("devboost.modules.ddev.is_interactive", lambda: True)
    ex = _no_brew_formulae(tmp_path / "ca")
    Ddev().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "tap", "ddev/ddev"] in ex.calls
    assert ["brew", "install", "--formula", "-y", "ddev/ddev/ddev"] in ex.calls
    assert ["brew", "install", "--formula", "-y", "mkcert"] in ex.calls
    i = ex.calls.index(["mkcert", "-install"])
    assert ex.interactives[i] is True
    assert not any(c[0] == "sudo" for c in ex.calls)


def test_ddev_unattended_leaves_the_ca_to_the_user(tmp_path: Path) -> None:
    ex = _no_brew_formulae(tmp_path / "ca")  # pytest's stdin is not a tty
    with pytest.raises(NeedsUser, match="mkcert -install"):
        Ddev().install(Ctx(os=MAC, ex=ex))
    assert ["mkcert", "-install"] not in ex.calls


def test_ddev_verify_needs_both_formulae_and_the_ca(tmp_path: Path) -> None:
    ca = tmp_path / "ca"
    ca.mkdir()
    (ca / "rootCA.pem").write_text("pem", encoding="utf-8")
    ready = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{ca}\n")})
    assert Ddev().verify(Ctx(os=MAC, ex=ready)) is True
    no_ca = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{tmp_path}/x\n")})
    assert Ddev().verify(Ctx(os=MAC, ex=no_ca)) is False


def test_ddev_update_upgrades_both_formulae(tmp_path: Path) -> None:
    ca = tmp_path / "ca"
    ca.mkdir()
    (ca / "rootCA.pem").write_text("pem", encoding="utf-8")
    ex = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{ca}\n")})
    Ddev().install(Ctx(os=MAC, ex=ex, force=True))
    assert ["brew", "upgrade", "--formula", "ddev", "mkcert"] in ex.calls
    assert not any(c[:2] == ["brew", "install"] for c in ex.calls)


def test_ddev_remote_and_playwright_are_portable() -> None:
    assert DdevRemote.portable and Playwright.portable


def _tailscale(home: Path, state: str | None, *, installed: bool = True) -> Scripted:
    cli = str(home / ".local" / "bin" / "tailscale")
    status = (Result(0, stdout=json.dumps({"BackendState": state})) if state
              else Result(1, stderr="The Tailscale GUI failed to start"))
    return Scripted(answers={
        ("brew", "list"): Result(0 if installed else 1),
        ("brew", "info"): Result(0, stdout='{"casks": [{"auto_updates": true}]}'),
        (cli, "status", "--json"): status,
    })


def test_tailscale_connected_is_done_and_its_cli_is_on_path(tmp_path: Path) -> None:
    Tailscale().install(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running")))
    cli = tmp_path / ".local" / "bin" / "tailscale"
    text = cli.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and f'exec "{APP_BIN}" "$@"' in text
    assert os.access(cli, os.X_OK)
    assert Tailscale().verify(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running"))) is True


def test_tailscale_installs_the_app_cask(tmp_path: Path) -> None:
    ex = _tailscale(tmp_path, "Running", installed=False)
    Tailscale().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "install", "--cask", "-y", "--adopt", "tailscale-app"] in ex.calls


def test_tailscale_joins_with_the_bundle_key_as_a_plain_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: "tskey-abc")
    ex = _tailscale(tmp_path, "NeedsLogin")
    Tailscale().install(Ctx(os=MAC, ex=ex))
    cli = str(tmp_path / ".local" / "bin" / "tailscale")
    assert [cli, "up", "--authkey=tskey-abc"] in ex.calls
    assert not any("--ssh" in c for c in ex.calls)
    assert not any(c[0] == "sudo" for c in ex.calls)


def test_tailscale_awaiting_approval_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: None)
    ex = _tailscale(tmp_path, None)
    with pytest.raises(NeedsUser, match="Network Extensions"):
        Tailscale().install(Ctx(os=MAC, ex=ex))
    assert ["open", "-a", "Tailscale"] in ex.calls
    assert Tailscale().verify(Ctx(os=MAC, ex=_tailscale(tmp_path, None))) is False


def test_playwright_on_macos_skips_the_system_libraries(tmp_path: Path) -> None:
    ex = Scripted()
    Playwright().install(Ctx(os=MAC, ex=ex))
    assert not any("dnf" in c or "install-deps" in c for c in ex.calls)
    assert ["npx", "--yes", "playwright", "install", "chromium",
            "chromium-headless-shell"] in ex.calls
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_ddev_tailscale_macos.py -v`
Expected: FAIL (`brew tap` not called — ddev takes its Fedora path; Tailscale runs the Linux `curl | sh`; Playwright runs `dnf`).

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/ddev.py` — imports: `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import ClassVar`, `from devboost.core.errors import InstallError, NeedsUser`, `BrewTap` added to the `devboost.model` import, `from devboost.modules._credentials import is_interactive`, `from devboost.modules.macos import Homebrew`. Then:

```python
#: ddev is not in homebrew-core; its own tap is the documented macOS install.
DDEV_TAP: pkg.Source = OsMap(macos=BrewTap("ddev/ddev"))


@dataclass(frozen=True)
class _DdevMac:
    """macOS (spec §2): ddev from its tap, mkcert from homebrew-core, and mkcert's local CA
    trusted once. Trusting the CA opens a macOS password dialog, so that step runs only
    when someone is there; otherwise the module is `blocked` with the one command to run."""

    uses_brew: ClassVar[bool] = True

    @staticmethod
    def _ca_ready(ctx: Ctx) -> bool:
        res = ctx.ex.run(["mkcert", "-CAROOT"])
        root = res.stdout.strip()
        return res.ok and bool(root) and (Path(root) / "rootCA.pem").is_file()

    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.installed(ctx, "ddev") and pkg.installed(ctx, "mkcert") and self._ca_ready(ctx)
        )

    def install(self, ctx: Ctx) -> None:
        present = [f for f in ("ddev", "mkcert") if pkg.installed(ctx, f)]
        if ctx.force and present:
            pkg.upgrade(ctx, *present)
        if "ddev" not in present:
            pkg.install(ctx, "ddev/ddev/ddev", source=DDEV_TAP)
        if "mkcert" not in present:
            pkg.install(ctx, "mkcert")
        if self._ca_ready(ctx):
            return
        if not is_interactive():
            raise NeedsUser(
                "mkcert's local CA is not trusted yet (HTTPS for ddev sites)",
                "run `mkcert -install` in a terminal — macOS asks for your password once",
            )
        res = ctx.ex.run(["mkcert", "-install"], interactive=True)
        if not res.ok:
            raise InstallError("ddev", "mkcert -install", res.code)
```

`Ddev`: `requires = (Docker, Homebrew)`, `per_os = OsMap(macos=_DdevMac())`, hand-off at the top of `verify` and `install`. `DdevRemote`: add `portable: ClassVar[bool] = True  # a no-op off headless hosts; the ddev CLI is the same`.

`engine/src/devboost/modules/server.py` — imports: `import json`, `from dataclasses import dataclass`, `from devboost.core.errors import NeedsUser` (extend), `from devboost.core.osinfo import OsMap`, `from devboost.modules._brew import BrewCask`, `from devboost.modules.macos import Homebrew`. After `_secret`:

```python
_TS_APP_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
#: Tailscale KB 1080: on macOS the CLI is the app binary, called by its real path. A
#: wrapper keeps that path (a symlink would not) and works in scripts, unlike an alias.
_TS_WRAPPER = (
    "#!/bin/sh\n"
    "# devboost — the Tailscale app's CLI. Managed by dev-boost (tailscale module).\n"
    f'exec "{_TS_APP_BIN}" "$@"\n'
)


def ts_cli() -> Path:
    return Path(os.environ["HOME"]) / ".local" / "bin" / "tailscale"


def _ts_state(ctx: Ctx) -> str:
    """BackendState from `tailscale status --json` ("Running", "NeedsLogin", …); "" if none."""
    res = ctx.ex.run([str(ts_cli()), "status", "--json"])
    try:
        data = json.loads(res.stdout) if res.stdout.strip() else None
    except ValueError:
        return ""
    state = data.get("BackendState") if isinstance(data, dict) else None
    return state if isinstance(state, str) else ""


@dataclass(frozen=True)
class _TailscaleMac:
    """macOS: the standalone app (cask `tailscale-app`), its CLI on PATH, and the one-time
    approval only the user can give. The Mac is a fleet client: no Tailscale SSH server."""

    uses_brew: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        return (
            BrewCask("tailscale-app").verify(ctx)
            and ts_cli().is_file()
            and _ts_state(ctx) == "Running"
        )

    def install(self, ctx: Ctx) -> None:
        BrewCask("tailscale-app").install(ctx)
        cli = ts_cli()
        if not cli.is_file() or cli.read_text(encoding="utf-8") != _TS_WRAPPER:
            cli.parent.mkdir(parents=True, exist_ok=True)
            cli.write_text(_TS_WRAPPER, encoding="utf-8")
            cli.chmod(0o755)
        state = _ts_state(ctx)
        if state == "Running":
            return
        key = _secret(ctx, "TAILSCALE_AUTHKEY")
        if key and state == "NeedsLogin" and ctx.ex.run([str(cli), "up", f"--authkey={key}"]).ok:
            return
        ctx.ex.run(["open", "-a", "Tailscale"])
        raise NeedsUser(
            "Tailscale is installed but not connected",
            "open Tailscale from the menu bar, allow its VPN configuration when macOS asks "
            "(System Settings → General → Login Items & Extensions → Network Extensions), "
            "then sign in — or add TAILSCALE_AUTHKEY to the secrets bundle",
        )
```

`Tailscale`: `requires = (Homebrew,)`, `per_os = OsMap(macos=_TailscaleMac())`, hand-off at the top of `verify` and `install` (Linux bodies unchanged).

`engine/src/devboost/modules/dev_stacks.py` — `Playwright`: add `portable: ClassVar[bool] = True  # npm + Playwright's own browser downloads; macOS needs no system libs`, and change the Fedora branch's `else:` to `elif ctx.os.family != "macos":` with this comment line above it: `# macOS: Chromium bundles its own frameworks — no system libraries to add.`

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"ddev"`, `"ddev-remote"`, `"playwright"`, `"tailscale"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_ddev_tailscale_macos.py tests/modules/test_docker_ddev.py tests/modules/test_server.py tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS; the Linux Tailscale/ddev/Playwright tests are unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/ddev.py src/devboost/modules/server.py src/devboost/modules/dev_stacks.py tests/modules/test_ddev_tailscale_macos.py tests/core/test_macos_contract.py
git commit -m "feat(macos): ddev via its tap + mkcert, Tailscale app with approval step, Playwright"
```

---

### Task 11: Verified-portable modules, `chezmoi-repo`, credential wording, native Claude notifications

Spec §2 per-OS rows `chezmoi-repo`, `claude-notify`, `pi-harness`; carry-over M3 item 3; D20, D21, D23.

**Files:**
- Modify: `engine/src/devboost/modules/claude_code.py`, `claude_mcp.py`, `claude_plugins.py`, `claude_skills.py`, `codex_code.py`, `codex_config.py`, `codex_mcp.py`, `codex_plugins.py`, `codex_skills.py`, `pi_harness.py`, `tpm.py` (`Tpm`, `TmuxPersist`), `_lsp.py` (`LspModule`), `dev_stacks.py` (`WebRuntimes`, `DevopsTools`, `Expo`, `DataServices`, `Aspire`, `DotnetLsp`), `base.py` (`ChezmoiRepo`), `shell.py` (`ClaudeNotify`); `dotfiles/private_dot_claude/hooks/executable_notify.sh`; `engine/tests/modules/test_base.py` (two chezmoi-repo tests); `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_portable_macos.py`, `engine/tests/dotfiles/test_claude_notify.py` (create)

**Interfaces:**
- Produces: `portable = True` on the classes listed in D20 (each with a one-line reason); `ChezmoiRepo` runs `chezmoi init --apply --force <repo>` and raises `NeedsUser` without a repo; the notify hook shows a native notification on Darwin.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_portable_macos.py`:

```python
"""Modules verified to run unchanged on macOS, and the chezmoi-repo / credential fixes."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.base import ChezmoiRepo
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.claude_mcp import ClaudeMcp
from devboost.modules.claude_plugins import ClaudePlugins
from devboost.modules.claude_skills import ClaudeSkills
from devboost.modules.codex_code import CodexCode
from devboost.modules.codex_config import CodexConfig
from devboost.modules.codex_mcp import CodexMcp
from devboost.modules.codex_plugins import CodexPlugins
from devboost.modules.codex_skills import CodexSkills
from devboost.modules.dev_stacks import (
    Aspire,
    DataServices,
    DevopsLsp,
    DevopsTools,
    DotnetLsp,
    Expo,
    LaravelLsp,
    PythonLsp,
    WebLsp,
    WebRuntimes,
)
from devboost.modules.editors import FreshLsp
from devboost.modules.pi_harness import PiHarness
from devboost.modules.shell import ClaudeNotify
from devboost.modules.tpm import TmuxPersist, Tpm
from tests.core.test_macos_contract import resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PORTABLE: list[type[Module]] = [
    ClaudeCode, ClaudeMcp, ClaudePlugins, ClaudeSkills, ClaudeNotify,
    CodexCode, CodexConfig, CodexMcp, CodexPlugins, CodexSkills, PiHarness,
    Tpm, TmuxPersist, WebRuntimes, DevopsTools, Expo, DataServices, Aspire, DotnetLsp,
    FreshLsp, PythonLsp, WebLsp, LaravelLsp, DevopsLsp, ChezmoiRepo,
]


@pytest.mark.parametrize("cls", PORTABLE)
def test_verified_portable(cls: type[Module]) -> None:
    assert cls.portable is True
    assert resolvable_on_macos(cls)


def test_chezmoi_repo_never_waits_on_a_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_DOTFILES_REPO", "https://github.com/user/dotfiles")
    ex = FakeExecutor()
    ChezmoiRepo().install(Ctx(os=MAC, ex=ex))
    assert ["chezmoi", "init", "--apply", "--force", "https://github.com/user/dotfiles"] in ex.calls


def test_chezmoi_repo_without_a_repo_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_DOTFILES_REPO", raising=False)
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path))  # no secrets bundle here
    with pytest.raises(NeedsUser, match="DEVBOOST_DOTFILES_REPO"):
        ChezmoiRepo().install(Ctx(os=FEDORA, ex=FakeExecutor(scripts={"age": Result(1)})))


def test_pi_harness_failure_points_at_the_real_github_auth() -> None:
    ex = FakeExecutor(scripts={"sh": Result(1)})
    with pytest.raises(ConfigError) as exc:
        PiHarness().install(Ctx(os=MAC, ex=ex))
    assert "gh auth status" in str(exc.value)
    assert "PAT from the secrets bundle" not in str(exc.value)
```

`tests/dotfiles/test_claude_notify.py`:

```python
"""The Claude notify hook: a native notification on macOS, ntfy wherever it is set."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = (Path(__file__).resolve().parents[3] / "dotfiles" / "private_dot_claude" / "hooks"
        / "executable_notify.sh")
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def _run(tmp_path: Path, uname: str, cwd: Path) -> Path:
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    log = tmp_path / "osascript.log"
    for name, body in (
        ("uname", f"echo {uname}"),
        ("osascript", f'printf "%s\\n" "$@" > "{log}"\ncat >> "{log}"'),
    ):
        exe = fake / name
        exe.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        exe.chmod(0o755)
    subprocess.run(
        ["bash", str(HOOK), "done"],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)},
        cwd=cwd, check=True, timeout=10,
    )
    return log


def test_macos_shows_a_native_notification_without_ntfy(tmp_path: Path) -> None:
    text = _run(tmp_path, "Darwin", tmp_path).read_text(encoding="utf-8")
    assert "Claude finished" in text
    assert f"cwd: {tmp_path}" in text
    assert "display notification (item 2 of argv) with title (item 1 of argv)" in text


def test_a_quote_in_the_path_stays_data(tmp_path: Path) -> None:
    odd = tmp_path / 'it"s'
    odd.mkdir()
    text = _run(tmp_path, "Darwin", odd).read_text(encoding="utf-8")
    assert f"cwd: {odd}" in text  # passed as an argument, never spliced into the script


def test_linux_has_no_native_notification(tmp_path: Path) -> None:
    assert not _run(tmp_path, "Linux", tmp_path).exists()


def test_hook_is_valid_bash() -> None:
    assert subprocess.run(["bash", "-n", str(HOOK)], check=False).returncode == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_portable_macos.py tests/dotfiles/test_claude_notify.py -v`
Expected: FAIL (`portable` is False; `--force` missing; `SecretsError` instead of `NeedsUser`; no `osascript` call).

- [ ] **Step 3: Implement**

Add one line to each class, right after `profiles` (import `ClassVar` from `typing` where the file lacks it):

```python
# ClaudeCode      portable: ClassVar[bool] = True  # npm under mise's node — same on macOS
# ClaudeMcp       portable: ClassVar[bool] = True  # only drives the claude CLI
# ClaudePlugins   portable: ClassVar[bool] = True  # ~/.claude/settings.json + the claude CLI
# ClaudeSkills    portable: ClassVar[bool] = True  # `npx skills add`
# ClaudeNotify    portable: ClassVar[bool] = True  # settings.json; the hook handles Darwin
# CodexCode       portable: ClassVar[bool] = True  # its install.sh handles darwin/aarch64
# CodexConfig     portable: ClassVar[bool] = True  # edits ~/.codex/config.toml
# CodexMcp        portable: ClassVar[bool] = True  # only drives the codex CLI
# CodexPlugins    portable: ClassVar[bool] = True  # only drives the codex CLI
# CodexSkills     portable: ClassVar[bool] = True  # `npx skills add`
# PiHarness       portable: ClassVar[bool] = True  # git clone (gh helper on macOS) + harness CLI
# Tpm             portable: ClassVar[bool] = True  # a git clone
# TmuxPersist     portable: ClassVar[bool] = True  # git clones
# WebRuntimes     portable: ClassVar[bool] = True  # mise; node/pnpm/bun ship darwin-arm64
# DevopsTools     portable: ClassVar[bool] = True  # mise + aqua (darwin-arm64 builds)
# Expo            portable: ClassVar[bool] = True  # a bundled template only
# DataServices    portable: ClassVar[bool] = True  # a bundled compose template only
# Aspire          portable: ClassVar[bool] = True  # `dotnet tool install` (~/.dotnet on PATH)
# DotnetLsp       portable: ClassVar[bool] = True  # `dotnet tool install` (~/.dotnet on PATH)
# ChezmoiRepo     portable: ClassVar[bool] = True  # `chezmoi init` — same on every OS
```

and on the base class in `_lsp.py`:

```python
class LspModule(Module):
    """Seed fresh's config and mise-pin the language servers listed in `servers_file`."""

    servers_file: ClassVar[str]
    category = "editors"
    #: mise-pinned servers (aqua / npm / pipx backends all have darwin-arm64 builds).
    portable: ClassVar[bool] = True
```

`base.py` — `ChezmoiRepo.install`: add `NeedsUser` to the `devboost.core.errors` import (drop `SecretsError` if nothing else uses it), and replace its end:

```python
        if not repo:
            raise NeedsUser(
                "chezmoi-repo: no dotfiles repo configured",
                "set DEVBOOST_DOTFILES_REPO=<git url> (or add DOTFILES_REPO to the secrets "
                "bundle) and re-run",
            )
        # --force: never stop at chezmoi's "overwrite?" prompt — under devboost's captured
        # stdio nobody sees it and the run hangs (same reason as the dotfiles module).
        if not ctx.ex.run(["chezmoi", "init", "--apply", "--force", repo]).ok:
            log.warn("chezmoi-repo: init/clone failed — dotfiles not synced (non-blocking)")
```

`tests/modules/test_base.py` — the chezmoi-repo tests change with the behaviour: the "no repo" test expects `pytest.raises(NeedsUser, match="DEVBOOST_DOTFILES_REPO")` (import `NeedsUser`), and the two argv assertions become `["chezmoi", "init", "--apply", "--force", "https://github.com/user/dotfiles"]`.

`claude_plugins.py` — replace the comment above `requires`:

```python
    # Secrets → git can authenticate to GitHub for the private clickup-flow marketplace
    # clone (gh's credential helper, or the bundle token in ~/.git-credentials on Linux —
    # one source: _credentials.github_credentials).
```

`pi_harness.py` — replace the "Bootstrap (HARD)" comment's first two lines and the error text:

```python
        # Bootstrap (HARD). Auth = whatever git already uses for GitHub, set up by the
        # `secrets` module: gh's credential helper (`gh auth setup-git`; macOS, gh users) or
        # the bundle token in ~/.git-credentials (Linux). One source:
        # _credentials.github_credentials. Shallow-clone the default branch just to obtain
        # install.sh; it then does the HARNESS_REF-pinned clone itself.
```

```python
            raise ConfigError(
                f"pi-harness: bootstrapping agent-harness ({repo}@{ref}) failed "
                f"(exit {res.code}) — check that git can read the private repo: "
                f"`gh auth status` (or the secrets-bundle token) needs access to {repo}"
            )
```

`shell.py` — `ClaudeNotify.description` becomes `"Notify on Claude task-done / needs-input: macOS notification + ntfy (phone)."`.

`dotfiles/private_dot_claude/hooks/executable_notify.sh` — full file:

```bash
#!/usr/bin/env bash
# Claude Code notification hook. Wired by the claude-notify module into
# ~/.claude/settings.json as the Stop hook (task finished) and Notification hook (Claude
# needs input).
#   - macOS: a native notification, always (no setup).
#   - ntfy (phone push): set DEVBOOST_NTFY_URL to a topic — e.g. https://ntfy.sh/<your-
#     private-topic> or your self-hosted ntfy behind Tailscale. Unset → skipped.
# Never blocks Claude: every step is best-effort and time-limited.

case "${1:-event}" in
  done)  title="✅ Claude finished";     prio="default" ;;
  input) title="⌨️ Claude needs input";  prio="high" ;;
  *)     title="Claude";                 prio="default" ;;
esac

# macOS: title and cwd reach AppleScript as arguments (`on run argv`), never spliced into
# the script text, so a quote in a path cannot break it.
if [ "$(uname -s)" = "Darwin" ] && command -v osascript >/dev/null 2>&1; then
  osascript - "${title}" "cwd: ${PWD}" >/dev/null 2>&1 <<'OSA' || true
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
OSA
fi

url="${DEVBOOST_NTFY_URL:-}"
[ -z "$url" ] && exit 0
command -v curl >/dev/null 2>&1 || exit 0

# --max-time keeps a slow/unreachable ntfy from ever stalling the shell; errors ignored.
curl -fsS --max-time 5 \
  -H "Title: ${title} — $(hostname)" \
  -H "Priority: ${prio}" \
  -H "Tags: robot" \
  -d "cwd: ${PWD}" \
  "$url" >/dev/null 2>&1 || true
exit 0
```

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"aspire"`, `"chezmoi-repo"`, `"claude-code"`, `"claude-mcp"`, `"claude-notify"`, `"claude-plugins"`, `"claude-skills"`, `"codex-code"`, `"codex-config"`, `"codex-mcp"`, `"codex-plugins"`, `"codex-skills"`, `"data-services"`, `"devops-lsp"`, `"devops-tools"`, `"dotnet-lsp"`, `"expo"`, `"fresh-lsp"`, `"laravel-lsp"`, `"pi-harness"`, `"python-lsp"`, `"tmux-persist"`, `"tpm"`, `"web-lsp"`, `"web-runtimes"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/dotfiles tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS. `KNOWN_GAPS` now holds exactly `aspire-gc`, `docker`, `docker-build-gc`, `obsidian-sync`, `pass`, `restic-b2`, `restic-backup` (fewer if P2 merged — Task 0).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules ../dotfiles/private_dot_claude/hooks/executable_notify.sh tests/modules tests/dotfiles/test_claude_notify.py tests/core/test_macos_contract.py
git commit -m "feat(macos): portable agent/LSP/dev-stack modules; chezmoi init --force; native Claude notifications"
```

---

### Task 12 (Z2): Default apps on macOS — a primitive M5 reuses, and the `utiluti` module

Zed spec "Default apps (macOS)"; carry-over Z2 item 2 (shared with M5's `default-apps`); D16–D18.

**Files:**
- Create: `engine/src/devboost/exec/primitives/default_apps.py`, `data/macos/default-apps.tsv`
- Modify: `engine/src/devboost/modules/cli_tools.py` (new `Utiluti`)
- Test: `engine/tests/primitives/test_default_apps.py` (create)

**Interfaces:**
- Produces (M5's `default-apps` module calls the same functions with its own rows):
  - `Association(ext: str, bundle_id: str)` (frozen dataclass).
  - `table(*parts: str) -> list[Association]` — rows of a bundled TSV (`ext<TAB>bundle id`).
  - `confirmation_required(os_info: OsInfo) -> bool` — macOS ≥ 26.4 (or unknown version).
  - `state_path() -> Path` — `$XDG_STATE_HOME/devboost/default-apps.json`.
  - `handled(rows: Sequence[Association]) -> bool` — every row's extension recorded for its app.
  - `apply(ctx, rows, *, can_prompt: bool) -> Outcome` — `Outcome(changed, already, refused, pending)`: lists of UTIs (`changed`, `already`, `refused`) and of extensions (`pending`). Raises `InstallError` when `utiluti` is missing.
  - `Utiluti(PackageModule)`: `name = "utiluti"`, `families = ("macos",)`, no profile (pulled in by `requires`).

- [ ] **Step 1: Write the failing tests** — `tests/primitives/test_default_apps.py`

```python
"""Default apps via utiluti: one dialog per UTI, asked once, only when someone can answer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import default_apps
from devboost.exec.primitives.default_apps import Association
from devboost.model import Ctx
from devboost.modules.cli_tools import Utiluti

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
ZED = "dev.zed.Zed"


class _LaunchServices(FakeExecutor):
    """utiluti over a fake LaunchServices: extension → UTI, UTI → default app."""

    def __init__(self, utis: dict[str, str], handlers: dict[str, str] | None = None,
                 refuse: set[str] | None = None) -> None:
        super().__init__(present={"utiluti"})
        self.utis = utis
        self.handlers = dict(handlers or {})
        self.refuse = refuse or set()
        self.sets: list[tuple[str, str, bool]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        a = list(argv)
        if a[:2] == ["utiluti", "get-uti"]:
            uti = self.utis.get(a[2])
            return Result(0, stdout=f"{uti}\n") if uti else Result(1)
        if a[:3] == ["utiluti", "type", "set"]:
            self.sets.append((a[3], a[4], interactive))
            if a[3] in self.refuse:
                return Result(1, stderr="declined")
            self.handlers[a[3]] = a[4]
            return Result(0)
        if a[:2] == ["utiluti", "type"]:
            app = self.handlers.get(a[2])
            return Result(0, stdout=f"{app}\n") if app else Result(1)
        return Result(0)


UTIS = {"yaml": "public.yaml", "yml": "public.yaml", "py": "public.python-script"}
ROWS = [Association(e, ZED) for e in ("yaml", "yml", "py")]


def test_the_bundled_table_has_the_zed_rows() -> None:
    rows = default_apps.table("data", "macos", "default-apps.tsv")
    zed = [r.ext for r in rows if r.bundle_id == ZED]
    assert {"md", "json", "py", "ts", "tsx", "php", "cs"} <= set(zed)
    assert len(zed) == len(set(zed))  # no duplicate extensions


@pytest.mark.parametrize(
    ("version", "asks"),
    [("27.0", True), ("26.4", True), ("26.3", False), ("15.6", False), ("", True)],
)
def test_confirmation_required_from_26_4(version: str, asks: bool) -> None:
    os_info = OsInfo("macos", "macos", "aarch64", version_id=version)
    assert default_apps.confirmation_required(os_info) is asks


def test_one_dialog_per_uti_and_every_extension_recorded() -> None:
    ex = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert sorted(ex.sets) == [("public.python-script", ZED, True), ("public.yaml", ZED, True)]
    assert sorted(out.changed) == ["public.python-script", "public.yaml"]
    assert default_apps.handled(ROWS)
    saved = json.loads(default_apps.state_path().read_text(encoding="utf-8"))
    assert saved == {ZED: ["py", "yaml", "yml"]}


def test_a_type_already_on_the_app_needs_no_dialog() -> None:
    ex = _LaunchServices(UTIS, handlers={"public.yaml": ZED, "public.python-script": ZED})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=False)
    assert ex.sets == [] and out.pending == []
    assert sorted(out.already) == ["public.python-script", "public.yaml"]
    assert default_apps.handled(ROWS)


def test_a_declined_type_is_never_asked_again() -> None:
    ex = _LaunchServices(UTIS, refuse={"public.python-script"})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.refused == ["public.python-script"]
    again = _LaunchServices(UTIS)
    default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == []


def test_nobody_to_answer_leaves_the_types_pending() -> None:
    ex = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=False)
    assert ex.sets == []
    assert sorted(out.pending) == ["py", "yaml", "yml"]
    assert not default_apps.handled(ROWS)


def test_missing_utiluti_is_an_install_error() -> None:
    with pytest.raises(InstallError, match="utiluti"):
        default_apps.apply(Ctx(os=MAC, ex=FakeExecutor()), ROWS, can_prompt=True)


def test_state_lives_under_xdg_state_home(tmp_path: Path) -> None:
    assert default_apps.state_path() == (
        tmp_path / ".local" / "state" / "devboost" / "default-apps.json"
    )


def test_utiluti_is_a_macos_brew_formula() -> None:
    assert Utiluti.families == ("macos",)
    ex = FakeExecutor()
    Utiluti().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "utiluti"]]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_default_apps.py -v`
Expected: FAIL with `ImportError: cannot import name 'default_apps'`.

- [ ] **Step 3: Implement**

Create `data/macos/default-apps.tsv` (repo root):

```
# macOS default apps — which app opens a file type (exec/primitives/default_apps.py).
# TAB-separated: extension <TAB> app bundle id. macOS 26.4+ asks the user to confirm each
# change, one dialog per UTI (extensions that share a UTI share one), once — dev-boost
# records what it asked in ~/.local/state/devboost/default-apps.json and never asks again.
# Z2 ships the Zed rows (code/text files a developer double-clicks); M5's `default-apps`
# module adds the other apps' rows. `.ts` is also MPEG transport-stream video on macOS;
# on a dev box TypeScript wins.
md	dev.zed.Zed
txt	dev.zed.Zed
log	dev.zed.Zed
json	dev.zed.Zed
yaml	dev.zed.Zed
yml	dev.zed.Zed
toml	dev.zed.Zed
sh	dev.zed.Zed
zsh	dev.zed.Zed
py	dev.zed.Zed
js	dev.zed.Zed
mjs	dev.zed.Zed
jsx	dev.zed.Zed
ts	dev.zed.Zed
tsx	dev.zed.Zed
php	dev.zed.Zed
cs	dev.zed.Zed
css	dev.zed.Zed
scss	dev.zed.Zed
sql	dev.zed.Zed
```

(Use real TAB characters between the columns. `scripts/build-bundle.sh` already bundles the whole `data/` directory.)

Create `engine/src/devboost/exec/primitives/default_apps.py`:

```python
"""Default apps on macOS — which app opens a file type — via `utiluti` (Apache-2.0).

Shared by the Zed module (Z2: code and text files open in Zed) and M5's `default-apps`
module; both read their rows from data/macos/default-apps.tsv.

macOS 26.4+ asks the user to confirm EVERY default-app change: one dialog per file type,
and the tool waits for the answer. So:
- a type is only changed when someone can answer (``can_prompt``);
- extensions that share a UTI (yaml/yml, …) cost one dialog, not one each;
- every extension dev-boost has handled is recorded in the state file, so a "no" is never
  asked again and a later change the user makes in Finder is never undone.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.resources import tsv_rows
from devboost.model import Ctx

UTILUTI = "utiluti"


@dataclass(frozen=True)
class Association:
    ext: str
    bundle_id: str


@dataclass
class Outcome:
    changed: list[str] = field(default_factory=list)  # UTIs now opening in the app
    already: list[str] = field(default_factory=list)  # UTIs that already did
    refused: list[str] = field(default_factory=list)  # declined, or no UTI for the extension
    pending: list[str] = field(default_factory=list)  # extensions waiting for a person


def table(*parts: str) -> list[Association]:
    """(extension, bundle id) rows of a bundled TSV (e.g. data/macos/default-apps.tsv)."""
    return [Association(c[0].lstrip("."), c[1]) for c in tsv_rows(*parts, min_cols=2)]


def confirmation_required(os_info: OsInfo) -> bool:
    """True from macOS 26.4, which shows a dialog per change; unknown versions assume so."""
    nums = [int(p) for p in os_info.version_id.split(".")[:2] if p.isdigit()]
    if not nums:
        return True
    return (nums[0], nums[1] if len(nums) > 1 else 0) >= (26, 4)


def state_path() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(
        Path(os.environ["HOME"]) / ".local" / "state"
    )
    return Path(state) / "devboost" / "default-apps.json"


def _load() -> dict[str, list[str]]:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(app): [e for e in exts if isinstance(e, str)]
        for app, exts in data.items()
        if isinstance(exts, list)
    }


def _save(data: dict[str, list[str]]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {app: sorted(set(exts)) for app, exts in data.items()}
    path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def handled(rows: Sequence[Association]) -> bool:
    """True when every row's extension has been handled for its app (set, kept, declined)."""
    seen = _load()
    return all(r.ext in seen.get(r.bundle_id, []) for r in rows)


def _ask(ctx: Ctx, *args: str) -> str | None:
    res = ctx.ex.run([UTILUTI, *args])
    out = res.stdout.strip()
    return out if res.ok and out else None


def apply(ctx: Ctx, rows: Sequence[Association], *, can_prompt: bool) -> Outcome:
    """Make each row's app the default for its extension; see the module docstring."""
    if not ctx.ex.which(UTILUTI):
        raise InstallError("default-apps", f"{UTILUTI} not found (brew install utiluti)", 127)
    seen = _load()
    out = Outcome()
    groups: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row.ext in seen.get(row.bundle_id, []):
            continue
        uti = _ask(ctx, "get-uti", row.ext)
        if uti is None:
            out.refused.append(row.ext)
            seen.setdefault(row.bundle_id, []).append(row.ext)
            continue
        groups.setdefault((row.bundle_id, uti), []).append(row.ext)
    for (app, uti), exts in groups.items():
        if _ask(ctx, "type", uti, "--bundle-id") == app:
            out.already.append(uti)
        elif not can_prompt:
            out.pending.extend(exts)
            continue
        elif ctx.ex.run([UTILUTI, "type", "set", uti, app], interactive=True).ok:
            out.changed.append(uti)
        else:
            out.refused.append(uti)
        seen.setdefault(app, []).extend(exts)
    _save(seen)
    return out
```

`engine/src/devboost/modules/cli_tools.py` — after `Glow`:

```python
@register
class Utiluti(PackageModule):
    name = "utiluti"
    category = "cli"
    description = "utiluti — sets which app opens a file type (macOS default apps)."
    # Pulled in by modules that set default apps (Zed; M5's default-apps). macOS only.
    families: ClassVar[tuple[str, ...]] = ("macos",)
    cmd = "utiluti"
    fedora_pkg = "utiluti"  # never used: the module only exists on macOS
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/primitives/test_default_apps.py tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ../data/macos/default-apps.tsv src/devboost/exec/primitives/default_apps.py src/devboost/modules/cli_tools.py tests/primitives/test_default_apps.py
git commit -m "feat(macos): default-apps primitive on utiluti — one dialog per type, asked once"
```

---

### Task 13 (Z2): Zed on macOS — cask, config, code/text files open in Zed

Zed spec rows "Install" and "Default apps (macOS)", Z2; carry-over Z2 item 1.

**Files:**
- Modify: `engine/src/devboost/modules/_zed.py`, `engine/src/devboost/modules/editors.py` (`Zed`, `zed_install_steps`), `engine/tests/modules/test_zed_module.py`, `engine/tests/modules/test_zed_config.py`; `dotfiles/.chezmoiignore` only if Task 0 found a `.config/zed` line in its Darwin block
- Test: `engine/tests/modules/test_zed_macos.py`, `engine/tests/dotfiles/test_zed_seed_macos.py` (create)

**Interfaces:**
- Consumes: `BrewCask` (Task 2), `default_apps` (Task 12), `Utiluti` (Task 12), `Homebrew` (Task 3), `is_interactive` (M1), M2's `chezmoi_apply` fixture (`tests/dotfiles/conftest.py`).
- Produces: `_zed.SUPPORTED_FAMILIES == ("fedora", "debian", "arch", "macos")`; `_zed.ZED_BUNDLE_ID = "dev.zed.Zed"`; `_zed.default_app_rows()`, `_zed.default_apps_done() -> bool`, `_zed.ensure_default_apps(ctx) -> None` (raises `NeedsUser` while types are pending); `Zed.per_os.macos == BrewCask("zed")`, `Zed.requires == (Homebrew, Utiluti)`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_zed_macos.py`:

```python
"""Z2: Zed on macOS — the cask, the same seeded config, and Zed as the default app."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.registry import load
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _zed
from devboost.modules._brew import BrewCask
from devboost.modules.cli_tools import Utiluti
from devboost.modules.editors import Zed
from devboost.modules.macos import Homebrew
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC_26_3 = OsInfo("macos", "macos", "aarch64", version_id="26.3")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _mac(cask_installed: bool = False) -> Scripted:
    """brew + utiluti: every extension has its own UTI; nothing opens in Zed yet."""
    answers: dict[tuple[str, ...], Result] = {
        ("brew", "list"): Result(0 if cask_installed else 1),
    }
    for row in _zed.default_app_rows():
        uti = f"test.{row.ext}"
        answers[("utiluti", "get-uti", row.ext)] = Result(0, stdout=f"{uti}\n")
        answers[("utiluti", "type", uti, "--bundle-id")] = Result(1)
    return Scripted(present={"utiluti"}, answers=answers)


def _sets(ex: Scripted) -> list[int]:
    return [i for i, c in enumerate(ex.calls) if c[:3] == ["utiluti", "type", "set"]]


def test_zed_is_managed_on_macos(tmp_path: Path) -> None:
    assert "macos" in Zed.families
    assert Zed.per_os.macos == BrewCask("zed")
    assert Homebrew in Zed.requires and Utiluti in Zed.requires
    assert build_plan(["zed"], load(), MAC, gpu_marker=tmp_path / "x") == [PlannedModule("zed")]


def test_mac_install_uses_the_cask_seeds_the_config_and_sets_default_apps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    ex = _mac()
    Zed().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "install", "--cask", "-y", "--adopt", "zed"] in ex.calls
    assert _zed.settings_path().is_file() and _zed.keymap_path().is_file()
    sets = _sets(ex)
    assert len(sets) == len(_zed.default_app_rows())  # one UTI per extension here
    assert all(ex.interactives[i] for i in sets)  # the dialog needs the terminal
    assert ex.calls[sets[0]][-1] == _zed.ZED_BUNDLE_ID
    assert Zed().verify(Ctx(os=MAC, ex=Scripted())) is True


def test_unattended_run_on_27_configures_zed_and_leaves_default_apps_to_the_user() -> None:
    ex = _mac(cask_installed=True)  # pytest's stdin is not a tty
    with pytest.raises(NeedsUser, match="devboost install zed"):
        Zed().install(Ctx(os=MAC, ex=ex))
    assert _zed.settings_path().is_file()  # the config was done first
    assert _sets(ex) == []
    assert Zed().verify(Ctx(os=MAC, ex=Scripted())) is False


def test_before_26_4_no_dialog_so_no_person_is_needed() -> None:
    ex = _mac(cask_installed=True)
    Zed().install(Ctx(os=MAC_26_3, ex=ex))
    assert _sets(ex)


def test_linux_zed_never_touches_brew_or_default_apps() -> None:
    ex = Scripted(answers={("mktemp", "-d"): Result(0, stdout="/tmp/z\n")})
    Zed().install(Ctx(os=FEDORA, ex=ex))
    assert not any(c[0] in ("brew", "utiluti") for c in ex.calls)
```

`tests/dotfiles/test_zed_seed_macos.py`:

```python
"""The Zed seed (create_ files) is applied on macOS too — same ~/.config/zed path."""

from __future__ import annotations

from .conftest import Apply


def test_chezmoi_seeds_zed_on_macos(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("darwin", "macos")
    assert (home / ".config" / "zed" / "settings.json").is_file()
    assert (home / ".config" / "zed" / "keymap.json").is_file()
```

Update the Z1 tests whose intent Z2 changes:

- `tests/modules/test_zed_module.py::test_zed_is_gui_and_dropped_on_macos_until_z2` → rename to `test_zed_is_gui_and_skipped_on_headless_hosts` and delete its `assert build_plan(["zed"], modules, MAC) == []` line (the macOS plan is covered by `test_zed_is_managed_on_macos`).
- `tests/modules/test_zed_config.py`: in `test_supported_families_is_the_single_source_for_zed_families` expect `("fedora", "debian", "arch", "macos")`; replace `MAC_CTX` with an unsupported family so the guard keeps its test — `OFF_CTX = Ctx(os=OsInfo("freebsd", "freebsd", "x86_64"), ex=FakeExecutor())` — and use it in `test_lsp_hook_does_nothing_on_macos` (rename `..._off_family`) and `test_ensure_config_does_nothing_off_family`. Add:

```python
def test_lsp_hook_merges_on_macos(home: Path) -> None:
    p = _zed.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(_NEEDS_MERGE, encoding="utf-8")
    mac = Ctx(os=OsInfo("macos", "macos", "aarch64", version_id="27.0"), ex=FakeExecutor())
    _zed.refresh_after_lsp(mac, all_pins())
    assert "agent_servers" in p.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_zed_macos.py tests/modules/test_zed_module.py tests/modules/test_zed_config.py tests/dotfiles/test_zed_seed_macos.py -v`
Expected: FAIL (`"macos" not in Zed.families`; `default_app_rows` missing).

- [ ] **Step 3: Implement**

`engine/src/devboost/modules/_zed.py`:
- Module docstring: replace the "Z2 (macOS) seam: …" paragraph with "macOS (Z2) uses the same config files and paths; the Zed module installs the cask and makes Zed the default app for code/text files (`ensure_default_apps`)." and the first line's "(Linux now; macOS Z2 reuses it unchanged)" with "(Linux and macOS)".
- Imports: `from devboost.core.errors import NeedsUser`, `default_apps` added to the `devboost.exec.primitives` import, `from devboost.modules._credentials import is_interactive`.
- `SUPPORTED_FAMILIES`:

```python
#: The OS families Zed is managed on. The single source for Zed.families and for every
#: path that writes Zed config on another module's behalf.
SUPPORTED_FAMILIES: tuple[str, ...] = ("fedora", "debian", "arch", "macos")
```

- At the end of the file:

```python
ZED_BUNDLE_ID = "dev.zed.Zed"
_DEFAULT_APPS = ("data", "macos", "default-apps.tsv")


def default_app_rows() -> list[default_apps.Association]:
    """The file types that open in Zed on macOS (the Zed rows of the shared table)."""
    return [r for r in default_apps.table(*_DEFAULT_APPS) if r.bundle_id == ZED_BUNDLE_ID]


def default_apps_done() -> bool:
    return default_apps.handled(default_app_rows())


def ensure_default_apps(ctx: Ctx) -> None:
    """macOS: code and text files open in Zed (Zed spec "Default apps").

    macOS 26.4+ asks the user to confirm each file type, so the change is only attempted
    when someone is there; an unattended run raises NeedsUser (Zed itself is done).
    """
    rows = default_app_rows()
    confirm = default_apps.confirmation_required(ctx.os)
    can_prompt = is_interactive() or not confirm
    if can_prompt and confirm and not default_apps.handled(rows):
        log.info("zed: macOS will ask you to confirm Zed as the default app, once per file type")
    out = default_apps.apply(ctx, rows, can_prompt=can_prompt)
    if out.refused:
        log.warn(
            f"zed: not the default app for {', '.join(out.refused)} — "
            "change it in Finder › Get Info › Open with, if you want"
        )
    if out.pending:
        raise NeedsUser(
            f"Zed is not yet the default app for {len(out.pending)} code/text file types",
            "run `devboost install zed` in a terminal — macOS asks you to confirm each "
            "file type once",
        )
```

`engine/src/devboost/modules/editors.py`:
- Imports: `from devboost.modules._brew import BrewCask`, `from devboost.modules.cli_tools import Utiluti`, `from devboost.modules.macos import Homebrew`.
- `zed_install_steps`: the macOS message becomes `"zed: macOS installs the Homebrew cask (Zed.per_os)"` (still contains "cask", so Z1's test holds).
- `Zed`:

```python
@register
class Zed(Module):
    name = "zed"
    category = "editors"
    description = "Zed — default GUI editor; curated settings, in-editor agents, pinned LSPs."
    gui = True
    profiles = ("editors",)
    families = _zed.SUPPORTED_FAMILIES
    #: macOS only (Linux plans drop both): the cask comes from brew; utiluti makes Zed the
    #: default app for code/text files.
    requires = (Homebrew, Utiluti)
    per_os = OsMap(macos=BrewCask("zed"))

    @staticmethod
    def _installed(ctx: Ctx) -> bool:
        # The script's symlink is checked directly: ~/.local/bin may not be on PATH yet in
        # the install session (same reason DotnetLsp checks ~/.dotnet/tools).
        return (_zed.home() / ".local" / "bin" / "zed").exists() or ctx.ex.which("zed")

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx) and _zed.config_ok(all_pins()) and _zed.default_apps_done()
        return self._installed(ctx) and _zed.config_ok(all_pins())

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)  # BrewCask: installs when missing; Zed updates itself
            _zed.ensure_config(ctx, all_pins())
            _zed.ensure_default_apps(ctx)
            return
        if not self._installed(ctx):
            self._run_installer(ctx)
        _zed.ensure_config(ctx, all_pins())
```

(`_run_installer` is unchanged.)

- [ ] **Step 4: If Task 0 found `.config/zed` in the Darwin block of `dotfiles/.chezmoiignore`, delete that line** (M2's temporary guard, carry-over Z2 item 1). Otherwise skip this step. The seed test above must pass either way.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/modules/test_zed_macos.py tests/modules/test_zed_module.py tests/modules/test_zed_config.py tests/dotfiles tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS (`test_zed_seed_macos` skips only if chezmoi is absent).

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/_zed.py src/devboost/modules/editors.py ../dotfiles/.chezmoiignore tests/modules/test_zed_macos.py tests/modules/test_zed_module.py tests/modules/test_zed_config.py tests/dotfiles/test_zed_seed_macos.py
git commit -m "feat(zed): Zed on macOS — cask, seeded config, default app for code and text files"
```

---

### Task 14: `env.sh` — `DOTNET_ROOT` on macOS and the `local.sh` override hook

Carry-over Z2 item 3; D12, D19.

**Files:**
- Modify: `dotfiles/dot_config/devboost/env.sh`
- Test: `engine/tests/dotfiles/test_env_overrides.py` (create)

**Interfaces:**
- Produces: on Darwin, when `~/.dotnet/dotnet` is executable, `DOTNET_ROOT` (default `$HOME/.dotnet`) is exported and `~/.dotnet` is on PATH. As its **last** step, `env.sh` sources `~/.config/devboost/local.sh` when readable — the user's file for `EDITOR`/`VISUAL` and any other override, in every shell.

- [ ] **Step 1: Write the failing tests** — `tests/dotfiles/test_env_overrides.py`

```python
"""env.sh: the user's local.sh wins; DOTNET_ROOT for the user .NET SDK on macOS."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENV_SH = Path(__file__).resolve().parents[3] / "dotfiles" / "dot_config" / "devboost" / "env.sh"
SHELLS = [s for s in ("sh", "bash", "zsh") if shutil.which(s)]


def _env(shell: str, home: Path, uname: str, keys: list[str]) -> dict[str, str]:
    fake = home / "bin"
    fake.mkdir(exist_ok=True)
    exe = fake / "uname"
    exe.write_text(f"#!/bin/sh\necho {uname}\n", encoding="utf-8")
    exe.chmod(0o755)
    fields = " ".join(f'"${{{k}-<unset>}}"' for k in keys)
    out = subprocess.run(
        [shell, "-c", f'. "{ENV_SH}"; printf "%s\\n" {fields}'],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(home)},
        capture_output=True, text=True, check=True,
    )
    return dict(zip(keys, out.stdout.splitlines(), strict=True))


@pytest.mark.parametrize("shell", SHELLS)
def test_local_sh_overrides_editor_and_visual(shell: str, tmp_path: Path) -> None:
    local = tmp_path / ".config" / "devboost" / "local.sh"
    local.parent.mkdir(parents=True)
    local.write_text('export EDITOR=nvim\nexport VISUAL="code --wait"\n', encoding="utf-8")
    env = _env(shell, tmp_path, "Darwin", ["EDITOR", "VISUAL"])
    assert env == {"EDITOR": "nvim", "VISUAL": "code --wait"}


@pytest.mark.parametrize("shell", SHELLS)
def test_without_local_sh_the_defaults_stand(shell: str, tmp_path: Path) -> None:
    assert _env(shell, tmp_path, "Linux", ["EDITOR"]) == {"EDITOR": "fresh"}


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_exports_dotnet_root_for_the_user_sdk(shell: str, tmp_path: Path) -> None:
    assert _env(shell, tmp_path, "Darwin", ["DOTNET_ROOT"]) == {"DOTNET_ROOT": "<unset>"}
    sdk = tmp_path / ".dotnet"
    sdk.mkdir()
    (sdk / "dotnet").write_text("#!/bin/sh\n", encoding="utf-8")
    (sdk / "dotnet").chmod(0o755)
    env = _env(shell, tmp_path, "Darwin", ["DOTNET_ROOT", "PATH"])
    assert env["DOTNET_ROOT"] == str(sdk)
    assert str(sdk) in env["PATH"].split(":")
    assert _env(shell, tmp_path, "Linux", ["DOTNET_ROOT"]) == {"DOTNET_ROOT": "<unset>"}


def test_env_sh_is_still_posix() -> None:
    assert subprocess.run(["sh", "-n", str(ENV_SH)], check=False).returncode == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_env_overrides.py -v`
Expected: FAIL (`EDITOR` stays `fresh`; `DOTNET_ROOT` unset). If Task 0 found an existing `local.sh` hook, `test_local_sh_overrides_editor_and_visual` already passes — keep it; only the `.NET` part then needs Step 3.

- [ ] **Step 3: Implement** in `dotfiles/dot_config/devboost/env.sh`

Inside the existing `if [ "$(uname -s)" = "Darwin" ]; then … fi` block (M2), after the `ANDROID_HOME` line — so it runs before `unset -f _devboost_path_prepend`:

```sh
  # dotnet-install.sh puts the SDK in ~/.dotnet (dotnet-sdk module). A .NET app host
  # (csharp-ls, aspire) finds the runtime only through DOTNET_ROOT, never through PATH.
  if [ -x "${HOME}/.dotnet/dotnet" ]; then
    export DOTNET_ROOT="${DOTNET_ROOT:-${HOME}/.dotnet}"
    _devboost_path_prepend "${HOME}/.dotnet"
  fi
```

At the very end of the file (skip if Task 0 found a hook already):

```sh

# ---------------------------------------------------------------------------
# Your overrides — ~/.config/devboost/local.sh is yours: chezmoi does not manage it and
# dev-boost never writes it. Sourced last, so e.g. `export EDITOR=nvim VISUAL=nvim` wins
# in every shell (bash, zsh, and `bash -lc` launchers). POSIX sh, like this file.
# ---------------------------------------------------------------------------
if [ -r "${HOME}/.config/devboost/local.sh" ]; then
  . "${HOME}/.config/devboost/local.sh"
fi
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/dotfiles -v`
Expected: PASS, including M2's `test_env_paths.py` / `test_env_sh.py` (their `HOME`s have no `~/.dotnet/dotnet` and no `local.sh`, so nothing changes for them).

- [ ] **Step 5: Commit**

```bash
git add ../dotfiles/dot_config/devboost/env.sh tests/dotfiles/test_env_overrides.py
git commit -m "feat(dotfiles): ~/.config/devboost/local.sh overrides; DOTNET_ROOT for the macOS SDK"
```

---

### Task 15: The `macos` profile is the workstation; `KNOWN_GAPS` names its owners

Spec §2 Profiles (`macos`), §9 (contract test); D1, D25.

**Files:**
- Modify: `profiles.toml` (`macos`), `engine/tests/core/test_macos_contract.py`

**Interfaces:**
- Produces: `macos` = `base, cli, shell, editors, python, web, laravel, dotnet, data, devops, react-native, apps, dev-hygiene, remote, claude, codex, pi` (M5 appends `macos-desktop`). `KNOWN_GAPS: dict[str, str]` (module → `"M4"` / `"M5"` / `"P2"`).

- [ ] **Step 1: Rewrite the contract test's gap list and the M2 profile test.** In `tests/core/test_macos_contract.py`:

Module docstring:

```python
"""Every module must have a macOS answer: installable, dropped, provided, or a known gap.

KNOWN_GAPS maps each module with no macOS path yet to the milestone that brings it
(spec §11). M2 cleared the terminal set and M3 the catalog; what is left is the Docker
runtime and the launchd timers (M4, each declared `MacosPending`) and pass (P2). A new
module must arrive with its macOS answer; the map must be empty by the end of M5 (§9).
"""
```

Replace the `KNOWN_GAPS` frozenset (whatever names are left in it after Task 11) with:

```python
KNOWN_GAPS: dict[str, str] = {
    "aspire-gc": "M4",
    "docker": "M4",
    "docker-build-gc": "M4",
    "obsidian-sync": "M4",
    "pass": "P2",  # drop this line if P2 has merged (Task 0)
    "restic-b2": "M4",
    "restic-backup": "M4",
}
```

In the two existing tests use the keys as a set: `new = unresolved() - set(KNOWN_GAPS)` and `fixed = set(KNOWN_GAPS) - unresolved()`. Replace M2's `test_the_macos_profile_plans_cleanly_on_a_mac` with the tests below, and add the owner test (the file already has `_plan`, `MAC`, `FEDORA` from M2 Task 12):

```python
def test_known_gaps_have_an_owner() -> None:
    assert set(KNOWN_GAPS.values()) <= {"M4", "M5", "P2"}


def test_the_macos_profile_plans_the_workstation(tmp_path: Path) -> None:
    modules = load()
    reasons = {p.name: p.skip_reason for p in _plan("macos", MAC, tmp_path)}
    gaps = {n for n in reasons if not resolvable_on_macos(modules[n])}
    assert gaps <= set(KNOWN_GAPS), sorted(gaps - set(KNOWN_GAPS))
    assert not [n for n, r in reasons.items() if r == "unsupported-os"]
    for want in (
        "xcode-clt", "homebrew", "rosetta", "zed", "fresh", "herdr", "herdr-plugins", "glow",
        "dotnet-sdk", "aspire", "android-sdk", "expo", "ddev", "uv", "web-runtimes",
        "tailscale", "mosh", "obsidian", "bruno", "claude-code", "codex-code", "pi-harness",
        "ghostty", "zsh-config", "dotfiles",
    ):
        assert reasons.get(want, "missing") is None, want
    assert reasons["flameshot"] == reasons["curl"] == "provided-by-macos"
    for gone in ("gearlever", "rpmfusion", "flatpak", "pass-store", "bash-config", "wezterm"):
        assert gone not in reasons, gone


def test_the_macos_profile_covers_the_terminal_set(tmp_path: Path) -> None:
    mac = {p.name for p in _plan("macos", MAC, tmp_path)}
    assert {p.name for p in _plan("terminal", MAC, tmp_path)} <= mac


def test_the_linux_workstation_gains_only_glow_and_herdr_plugins(tmp_path: Path) -> None:
    names = {p.name for p in _plan("full", FEDORA, tmp_path)}
    assert {"glow", "herdr-plugins"} <= names
    assert not {"xcode-clt", "homebrew", "rosetta", "utiluti", "zsh-config"} & names
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_macos_contract.py -v`
Expected: FAIL — `test_the_macos_profile_plans_the_workstation` (`macos` is still `["terminal"]`, so `zed`, `ddev`, … are missing).

- [ ] **Step 3: Expand the profile** — `profiles.toml`, replace the `macos` entry and its comment:

```toml
# macOS workstation default (`devboost install` on a Mac) — spec §2 Profiles. Linux-only
# members fall out via `families`; macOS-provided ones report provided-by-macos. M5
# appends "macos-desktop"; the Docker runtime and launchd timers report blocked until M4.
macos = ["base","cli","shell","editors","python","web","laravel","dotnet","data",
         "devops","react-native","apps","dev-hygiene","remote","claude","codex","pi"]
```

- [ ] **Step 4: Run the whole gate**

Run: `uv run ruff check && uv run mypy && uv run pytest -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add ../profiles.toml tests/core/test_macos_contract.py
git commit -m "feat(macos): the macos profile is the full workstation; known gaps name their milestone"
```

---

### Task 16: Docs, spec sync, full gate, and the acceptance run on this Mac

Spec §10 (each PR ships its docs).

**Files:**
- Modify: `docs/macos.md` (M2 created it), `docs/zed.md`, `docs/adding-a-module.md`, `docs/agents.md`, `docs/remote-fleet.md`, `README.md`, `CHANGELOG.md`, `docs/superpowers/specs/2026-09-18-macos-support-design.md`, `docs/superpowers/specs/2026-09-18-zed-default-editor-design.md`

- [ ] **Step 1: `docs/macos.md`** — edit M2's page:

1. Status line: `**Status: M3 — the workstation.** `devboost install` (the `macos` profile) installs the whole catalog; Docker and the scheduled jobs arrive in M4, the desktop layer in M5, `curl … | bash` in M6.`
2. `## Requirements` — replace the Homebrew/CLT bullet with: `- To run from a clone (until M6's installer): the Command Line Tools for git (`xcode-select --install`) and uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`). dev-boost itself installs and maintains the CLT, Homebrew (analytics off) and Rosetta 2.`
3. `## Install from a clone` — the commands become `uv run devboost install --dry-run` / `uv run devboost install` (the default profile on a Mac is `macos`).
4. Replace `## What you get` with:

```markdown
## What you get

| Kind | Modules |
|---|---|
| Foundation | `xcode-clt` (silent CLT install), `homebrew` (analytics off), `rosetta` (macOS ≤ 27) |
| Homebrew formulae | the terminal set (M2), plus glow, mosh, neovim (opt-in), uv, cmake (`build-tools`), smartmontools, ffmpeg (`multimedia`), utiluti, mkcert, ddev (`ddev/ddev` tap) |
| Homebrew casks | ghostty, nerd-fonts, zed, obsidian, bruno, bitwarden, localsend, vlc, tailscale-app, android-commandlinetools; opt-in: visual-studio-code, jetbrains-toolbox, wezterm@nightly |
| Own installers | .NET 10 SDK in `~/.dotnet` (`dotnet-install.sh`), herdr 0.9.1 (pinned, SHA-256-checked), Claude Code, Codex, the Pi harness |
| Same as Linux | mise runtimes (node/pnpm/bun, java, devops tools), LSP servers, Playwright, Aspire, csharp-ls, the Claude/Codex plugins, skills and MCP servers |
| Provided by macOS (skipped) | curl, unzip, wl-clipboard, flameshot (⌘⇧5), fwupd, thermald, power-profiles-daemon, va-hwaccel |
| Linux-only (not planned) | bash-config, gearlever, earlyoom, gpu-detect, zram, the brain-host services, the Fedora system layer |

`devboost install --update` upgrades every Homebrew formula and cask in the plan, except
apps that update themselves (Zed, Ghostty, Obsidian, VS Code, Tailscale, …).
```

5. Add after `## Terminal — Ghostty`:

```markdown
## Editor — Zed

Zed is the default editor on macOS too (see [zed.md](zed.md)): the `zed` cask, the same
`~/.config/zed/settings.json` seed and must-have keys as Linux, and Zed as the app that
opens code and text files (`data/macos/default-apps.tsv`). macOS 26.4+ asks you to confirm
each file type once; dev-boost remembers what it asked (`~/.local/state/devboost/default-apps.json`)
and never asks again, even if you said no.

`$EDITOR` / `$VISUAL`: put your own choice in `~/.config/devboost/local.sh` (for example
`export EDITOR=nvim VISUAL=nvim`). It is yours — dev-boost never writes it — and it is read
last, in every shell.
```

6. Replace `## One-time manual steps` with:

```markdown
## One-time manual steps

A step only you can do is reported as **blocked** with the exact fix, and the rest of the
run carries on. Run `devboost install` again afterwards.

| When | What to do |
|---|---|
| `tailscale` blocked | Open Tailscale from the menu bar, allow its VPN configuration (System Settings → General → Login Items & Extensions → Network Extensions) and sign in — or add `TAILSCALE_AUTHKEY` to the secrets bundle. The Mac joins as a client (no Tailscale SSH server). |
| `ddev` blocked | Run `mkcert -install` in a terminal once; macOS asks for your password to trust the local CA. |
| `zed` blocked | Run `devboost install zed` in a terminal and answer the "use Zed?" dialogs (one per file type). |
| `xcode-clt` blocked | Rare: run `xcode-select --install` and click Install. |
| a cask is `present-unmanaged` | You installed that app by hand and Homebrew cannot take it over; dev-boost leaves it alone. |

## Not on macOS yet (M4)

`docker`, `docker-build-gc`, `aspire-gc`, `restic-backup`, `restic-b2` and `obsidian-sync`
report **blocked: not automated on macOS yet (lands in M4)** with a manual workaround;
`data-services`, `ddev` and `laravel-lsp` wait for Docker. Until then:
`brew install colima docker docker-compose && colima start`.
```

7. `## Troubleshooting` — add rows: `| csharp-ls / aspire: "You must install .NET" | open a new shell: env.sh exports DOTNET_ROOT=~/.dotnet |` and `| herdr --remote from the Mac disconnects right away | herdr < 0.8 on either end — run devboost install on both machines (pin 0.9.1) |`.
8. `## Coming next` — `M4 — Docker runtimes (Colima default) and launchd timers. M5 — desktop layer (defaults, AeroSpace, Raycast, default-apps, …) and the opt-in iOS profile. M6 — curl … | bash on a fresh Mac.`

- [ ] **Step 2: `docs/zed.md`** — replace the whole `## macOS (planned — milestone Z2)` section with:

```markdown
## macOS

Same files, same guarantees: `~/.config/zed/settings.json` and `keymap.json` are seeded
once (chezmoi `create_`), and the must-have keys are merged on every run
(`_zed.SUPPORTED_FAMILIES` includes `macos`). Zed comes from the `zed` Homebrew cask
(`Zed.per_os`), which also puts the `zed` CLI on PATH; Zed updates itself, so
`devboost install --update` leaves it alone.

**Default app.** Code and text files open in Zed: the Zed rows of
`data/macos/default-apps.tsv`, applied through `utiluti` (`exec/primitives/default_apps.py`,
shared with M5's `default-apps` module). macOS 26.4+ asks you to confirm every change, one
dialog per file type (extensions sharing a type share one), so dev-boost only tries when a
terminal is attached, asks each type once, and records it in
`~/.local/state/devboost/default-apps.json` — a "no" is never asked again. An unattended
run leaves `zed` **blocked** with "run `devboost install zed` in a terminal". `.ts` is also
MPEG transport-stream video on macOS; on a dev box it opens in Zed.

**Your own editor.** `~/.config/devboost/local.sh` is sourced last by `env.sh`; set
`EDITOR` / `VISUAL` there.
```

- [ ] **Step 3: `docs/adding-a-module.md`** — append to its `## macOS` section:

```markdown
- A module whose macOS install uses Homebrew **requires `Homebrew`** (`modules/macos.py`).
  `PackageModule` and `FlatpakApp` already do; a custom strategy that calls brew sets
  `uses_brew: ClassVar[bool] = True` and its module lists `Homebrew` in `requires`
  (`tests/core/test_homebrew_edges.py` enforces it). Linux plans drop Homebrew.
- A macOS path that a later milestone owns: `per_os = OsMap(macos=MacosPending("M4",
  "<manual workaround>"))` (`modules/_pending.py`). The module reports `blocked` on a Mac
  and stays in `KNOWN_GAPS` (module → milestone) until the real strategy lands.
- A pinned binary is keyed by OS **and** arch: `media.catalog.asset_key(ctx.os)` →
  `linux-x86_64`, `linux-aarch64`, `macos-aarch64`. Never key by arch alone.
- An installer script: `remote_script.run_script(ctx, name, url, "bash", *args)` —
  downloads into a private temp dir, then runs it.
- A step that opens a macOS dialog runs only when `_credentials.is_interactive()`;
  otherwise raise `NeedsUser(reason, how_to_fix)`.
- Default apps: add rows to `data/macos/default-apps.tsv` and call
  `default_apps.apply(ctx, rows, can_prompt=…)`.
```

- [ ] **Step 4: `docs/agents.md`** — in `## Pi`, replace "Requires the secrets-bundle GitHub PAT to have read access to the private harness repo." with "git must be able to read the private harness repo — through gh (`gh auth login`; macOS and gh users) or the secrets-bundle token (Linux)." (carry-over M3 item 3). In "Profiles at a glance" add a row `| cli (every OS) | … includes herdr + herdr-plugins (pinned, curated) and glow | yes |`, and one sentence under the table: "herdr and its pinned plugin set are installed by default on every OS (macOS included; Omarchy ships its own herdr). herdr is pinned to 0.9.1 per OS and arch in `catalog.toml`."

- [ ] **Step 5: `docs/remote-fleet.md`** — in `## 2. Per-role setup`, add a subsection:

```markdown
### A Mac as a fleet client

`devboost install` on a Mac installs the `remote` profile's client side: the Tailscale
app (`tailscale-app` cask; CLI at `~/.local/bin/tailscale`, no Tailscale SSH server — the
Mac serves nothing), `mosh`, and herdr 0.9.1. `herdr --remote <server>` pastes a clipboard
image into the remote pane on Ctrl+V (macOS screenshots go to the clipboard: ⌘⇧4, then
Ctrl+V). Keep herdr on the same release on both ends — the Mac client of herdr < 0.8
disconnects right after connecting.
```

- [ ] **Step 6: README and CHANGELOG** (repo root)

Regenerate the README tables with the same snippet M2 Task 13 Step 4 used (between the `BEGIN/END generated profiles table` markers, from `scripts/gen_profiles_table.py`), then `git diff --stat README.md`. Expected: the `base` row gains `xcode-clt`, `homebrew`, `rosetta`; `cli` gains `herdr-plugins`, `glow`; the `macos` row lists the workstation; the module table gains `xcode-clt`, `homebrew`, `rosetta`, `glow`, `utiluti`. Change the macOS install line to: "**macOS (Apple Silicon):** `devboost install` from a clone installs the workstation — see [docs/macos.md](docs/macos.md) (Docker in M4; `curl … | bash` in M6)."

`CHANGELOG.md`, under `## [Unreleased]`:

```markdown
### Added
- **macOS catalog (M3)** — `devboost install` on a Mac installs the workstation:
  `xcode-clt`, `homebrew`, `rosetta` modules; casks for the GUI apps; .NET 10 in `~/.dotnet`;
  Android SDK via the cmdline-tools cask; ddev (tap) + mkcert; the Tailscale app as a
  fleet client; herdr pinned per OS and arch; the agent CLIs, LSPs and dev stacks.
  Modules M4 owns (Docker, scheduled jobs) report `blocked` with a workaround.
- **Zed on macOS (Z2)** — `zed` cask, the same seeded config, and Zed as the default app
  for code/text files (`utiluti`; macOS 26.4+ asks once per file type).
- `glow` and `herdr-plugins` are in the `cli` profile on every OS.
- `~/.config/devboost/local.sh`: your own `EDITOR`/`VISUAL` and other overrides, read last.
- `devboost doctor`: Rosetta status (Intel-only apps from macOS 28).

### Changed
- herdr 0.7.5 → 0.9.1 on every OS; catalog pins are keyed `<os>-<arch>`.
- `devboost install --update` on macOS upgrades Homebrew casks too, except apps that
  update themselves.
- `chezmoi-repo` runs `chezmoi init --apply --force`; a missing repo URL is `blocked`,
  not a failure.
- The Claude notify hook also shows a native macOS notification.

### Fixed
- The executor finds mise's shims where mise puts them (`MISE_DATA_DIR`, `XDG_DATA_HOME`).
```

- [ ] **Step 7: Spec sync**

`docs/superpowers/specs/2026-09-18-macos-support-design.md`:
- Decisions table, "Desktop" row: `duti` → `utiluti`.
- §1 "Ordering": append "A strategy that uses brew declares `uses_brew = True`; `tests/core/test_homebrew_edges.py` enforces the edge. A macOS path owned by a later milestone is `MacosPending(milestone, workaround)` (reported `blocked`, still a gap)."
- §2 Formulae: `**duti**` → `**utiluti**` (duti is unmaintained; see the M3 plan D16).
- §2 per-OS table: herdr row → "catalog pin 0.9.1 keyed `<os>-<arch>` (`linux-x86_64`, `linux-aarch64`, `macos-aarch64`); `shasum`/`sha256sum`; `mkdir -p` + `install -m`"; tailscale row → "CLI through a `~/.local/bin/tailscale` wrapper that execs the app binary (Tailscale KB 1080)"; add a `build-tools` note "+ brew `cmake`".
- §2 New macOS-only modules, `default-apps` row: "utiluti table (`data/macos/default-apps.tsv`, shared with the Zed module) … macOS 26.4+ confirms each change: applied only when interactive, once per UTI, recorded in `~/.local/state/devboost/default-apps.json`".
- §2 Profiles: after the `macos` bullet add "(M3 ships it without `macos-desktop`; M5 appends it)"; `cli` bullet unchanged.
- §6: append "A named `brew upgrade --cask` is greedy in Homebrew 7, so dev-boost checks `auto_updates` first and skips those casks."
- §9 contract test: "`KNOWN_GAPS` maps each gap to its owning milestone."
- §11 M3 row, Outcome: "the workstation from a clone; Docker/timers `blocked` until M4 (with Z2)".

`docs/superpowers/specs/2026-09-18-zed-default-editor-design.md`:
- Decisions, "Default apps (macOS)": "`utiluti` (duti is unmaintained): code/text extensions open in Zed; macOS 26.4+ confirms each type — applied only when interactive, once per type, recorded; shared primitive with M5 `default-apps`".
- Rollout Z2 row, Notes: "shipped with macOS M3 (one PR)".

- [ ] **Step 8: Full gate** (from `engine/`)

Run: `uv run ruff check && uv run mypy && uv run pytest`
Expected: all green; skips only for tools absent on the host.

- [ ] **Step 9: Acceptance — `devboost install` from the clone on this Mac** (from `engine/`)

```bash
uv run devboost doctor
uv run devboost install --dry-run
```
Expected: doctor shows `rosetta: not installed — devboost install rosetta` (this Mac has none). The plan starts with `xcode-clt`, `homebrew`, `rosetta`; `curl`/`unzip`/`flameshot`/… are `provided-by-macos`; no `unsupported-os`, no traceback; no Linux-only module listed.

```bash
uv run devboost install
```
Expected: one sudo prompt, then: `homebrew` turns analytics off (this Mac's brew had them on), `rosetta` installs, the casks and formulae install; **blocked** (with their fix text): `docker`, `docker-build-gc`, `aspire-gc`, `obsidian-sync` (M4), and `data-services`, `ddev`, `laravel-lsp` (required docker); `tailscale` until you approve it; `pass` unless P2 has landed. In this interactive run, `zed` shows the "use Zed?" dialogs — answer them — and `ddev` would ask for `mkcert -install` only after Docker exists (M4).

```bash
uv run devboost verify macos
uv run devboost install            # second run: everything done reports skip; blocked stay blocked
brew analytics state               # "InfluxDB analytics are disabled."
arch -x86_64 /usr/bin/true && echo rosetta-ok
herdr --version                    # 0.9.1
~/.dotnet/dotnet --list-sdks       # a 10.0.x line
zsh -i -c 'echo $DOTNET_ROOT'      # /Users/<you>/.dotnet
utiluti type public.python-script --bundle-id   # dev.zed.Zed
glow ../README.md | head -5
uv run devboost install --update --dry-run      # casks listed; Zed/Ghostty/Obsidian skip as self-updating at run time
```

By hand: open a `.py` and a `.md` file from Finder → both open in Zed; `herdr --remote <a fleet server>` connects and a ⌘⇧4 screenshot pastes with Ctrl+V; approve Tailscale, re-run `devboost install`, and `tailscale status` shows the tailnet. Write the results (and every blocked line with its fix) into the PR description.

- [ ] **Step 10: Commit** (repo root)

```bash
git add docs/macos.md docs/zed.md docs/adding-a-module.md docs/agents.md docs/remote-fleet.md README.md CHANGELOG.md docs/superpowers/specs/2026-09-18-macos-support-design.md docs/superpowers/specs/2026-09-18-zed-default-editor-design.md
git commit -m "docs: macOS catalog (M3) and Zed on macOS (Z2) — macos.md, zed.md, module guide, specs"
```

- [ ] **Step 11: Before merge.** Shared files changed (`env.sh`, `profiles.toml` `cli`/`base`, the herdr pin, `chezmoi-repo`, the notify hook), so run the Fedora and Ubuntu VM rehearsal (`scripts/vm-test.sh`, `docs/vm-testing.md`) with `devboost install cli` and confirm `glow`, `herdr` 0.9.1 and `herdr-plugins` install there and a login shell is clean. Then hand off with superpowers:finishing-a-development-branch. PR title: `feat(macos): M3 catalog + Z2 Zed on macOS`. Commits and the PR carry no AI attribution (constitution).

---

## Coverage

| Requirement | Task |
|---|---|
| §11 M3: formulae / casks | 7, 8 (glow), 12 (utiluti) |
| §11 M3: custom-install `per_os.macos` | 9 (dotnet, android), 10 (ddev, tailscale, playwright), 7 (build-tools, smartmontools), 11 (portable sweep) |
| §11 M3: provided_by / families sweep | 6 |
| §11 M3: `xcode-clt`, `homebrew`, `rosetta` (+ §0 version rule, doctor) | 3, 4 |
| §11 M3: herdr pins + `herdr-plugins` / `glow` default | 8 |
| §11 M3: `macos` profile | 15 |
| §6: `--update` on macOS | 2 |
| Z2: cask + default apps (shared with M5) | 12, 13 |
| Carry-over M3: cask upgrade on `--update` | 2 |
| Carry-over M3: `(os, arch)` asset keying | 8 |
| Carry-over M3: claude_plugins / pi_harness credential text | 11 |
| Carry-over M3: executor mise shims path | 1 |
| Carry-over M3: `macos` profile expansion | 15 |
| Carry-over Z2: `SUPPORTED_FAMILIES`, `per_os` BrewCask, install routing, `.config/zed` ignore | 13 |
| Carry-over Z2: EDITOR/VISUAL override hook | 14 |
| §10 docs | 16 |
