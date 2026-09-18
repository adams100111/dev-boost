# macOS support — design

**Date:** 2026-09-18 · **Status:** approved (brainstorm + two grilling passes) ·
**Branch:** `feat/macos-support`
**Companion specs:** [pass multi-device](2026-09-18-pass-multi-device-design.md) ·
[Zed as default editor](2026-09-18-zed-default-editor-design.md). This spec ships first;
the companions depend on its engine (M1) for their macOS parts.

## Goal

Make an Apple Silicon Mac a **primary dev-boost workstation** — not a port of the Linux
setup, but the best 2026 macOS setup for this developer: Laravel (ddev), .NET + Aspire,
Python (uv), web (React/Next.js/Inertia/Tailwind), React Native (Android, and iOS opt-in),
Claude/Codex/Pi, herdr, zsh + chezmoi dotfiles, and a macOS-native desktop layer. Modeled
on the Omarchy/Arch backend (v0.1.80): one catalog, per-OS divergence as typed data, no
engine branching.

## Decisions

| Topic | Decision |
|---|---|
| Role | Primary workstation; full parity where it makes sense, Mac-native where better |
| Architecture | `macos` is a first-class family. `brew bundle` batching deferred; data model keeps it possible |
| Hardware | Apple Silicon only (`darwin-arm64`); Intel refused with a clear message |
| macOS versions | **Primary target macOS 27 Golden Gate** (released 2026-09-14; the author's Mac); also supported: 26 Tahoe. 15 Sequoia best-effort (Homebrew Tier 1, untested). Older → refused |
| Shell | zsh on macOS, bash on Linux; shared POSIX core; zsh-autosuggestions + zsh-syntax-highlighting |
| Terminal | **Ghostty default on every OS** (cross-OS change); foot stays on Omarchy (`provided_by`); WezTerm opt-in + deprecated |
| Docker | Colima (default) / OrbStack / Docker Desktop, switchable with full reconfigure |
| Desktop | `macos-defaults` (+ revert), maxfiles limit, firewall, Raycast, AeroSpace + AltTab, Thaw, MonitorControl + BetterDisplay, Keka, Stats, Quick Look plugins, `duti` |
| iOS | Opt-in `ios` profile (xcodes + simulator runtime + CocoaPods/watchman) |
| Secrets | gh + keychain for GitHub; age bundle optional (key in keychain); `pass` default (companion spec) |
| Editor | Zed default on every OS (companion spec); VS Code opt-in |
| herdr | `herdr` + `herdr-plugins` + `glow` default on every OS |
| Delivery | `get.sh` + frozen `devboost-darwin-arm64`; no Homebrew tap |
| Docs | Each milestone PR ships its docs; constitution v3.1.0 |

### Licensing constraints that shaped the choices

The Mac is used for employer and client work, so every default must be free for
commercial use:

- **OrbStack** — Free plan is personal, non-commercial only; freelance/employer/business
  use or >$10k/yr related income needs Pro ($8/user/mo). → not default.
- **Docker Desktop** — free only when the org the work is for has <250 employees **and**
  <$10M revenue. → not default.
- **Colima** — MIT. With ddev's default Mutagen sync, performance ≈ OrbStack. → default.
- **C# Dev Kit** — VS Community terms; enterprise orgs (>250 PCs or >$1M) may not use it
  without a paid VS subscription. → `csharp-ls` instead (Zed spec).
- **Shottr** — paid for commercial use. → not included (⌘⇧5 built-in).
- **Raycast Free** — explicitly allowed for commercial use. → included.
- **tart** (VM testing) — royalty-free on personal workstations. → used for rehearsal.

## 0. Supported macOS versions

| Version | Status | Notes |
|---|---|---|
| **27 Golden Gate** | primary, E2E-tested | Homebrew 7 Tier 1; last release with full Rosetta 2 |
| 26 Tahoe | supported, E2E-tested (tart) | Spotlight clipboard history (26.0), charge limit (26.4+) |
| 15 Sequoia | best-effort | Homebrew Tier 1; not in E2E matrix |
| ≤ 14 | refused | Homebrew 7 moved Sonoma to Tier 3 (no bottles / `.pkg`) |

Version-dependent behavior is data, keyed on `OsInfo.version_id` (major):
- **Rosetta:** `rosetta` module installs on ≤ 27; on ≥ 28 (Rosetta limited to legacy games)
  it is skipped with a `doctor` warning listing Intel-only apps
  (`system_profiler SPApplicationsDataType`, "Kind: Intel"). Colima's `--vz-rosetta`
  (fast amd64 containers) is enabled only when Rosetta is present; otherwise Colima uses
  its default qemu emulation for amd64 images and `doctor` notes the slowdown.
- `macos-defaults` keys and the tool casks are verified on 27 and 26 at M5 (§9); a key or
  app that misbehaves on a version is gated by a `min_version`/`max_version` field on its
  table row / module rather than removed.
- Homebrew 7: `HOMEBREW_NO_AUTO_UPDATE` is deprecated but functional — kept; the explicit
  once-per-run `brew update` makes it safe to drop later. `brew services` labels are now
  `sh.brew.<formula>`, so service checks use `brew services info --json <formula>`, never
  a hard-coded launchd label.
- App compatibility on 27 (checked at M5 on the real Mac): **Thaw** — macOS 27 support
  was in preview builds (minor menu-bar edge cases); if the stable cask misbehaves, the
  module is gated off on 27 with a doctor note rather than shipping a preview build.
  AeroSpace, AltTab, Colima and the other casks: no 27-specific issue found; confirmed or
  gated during M5.

## 1. Engine core

### `core/osinfo.py`
- `OsMap` gains `macos: T | None = None`, included in `get()` lookup.
- `detect()` on Darwin: `version_id` from `sw_vers -productVersion`; **`arch` normalized
  `arm64 → aarch64`** (herdr's asset picker and every `aarch64` lookup depend on it).
- `is_headless()` on Darwin: `False` unless in an SSH session (`SSH_CONNECTION`/`SSH_TTY`).
  The systemd-default-target fallback would mark every Mac headless and skip all GUI.

### `exec/executor.py`
- `RealExecutor` prepends `/opt/homebrew/bin:/opt/homebrew/sbin` to `PATH` on Darwin, so
  brew-installed tools resolve in a `curl|bash` run without brew shellenv.

### `exec/primitives/pkg.py` — `Brew`
- Brew binary `/opt/homebrew/bin/brew` (fallback `which brew`).
- Env on every call: `HOMEBREW_NO_AUTO_UPDATE=1`, `HOMEBREW_NO_INSTALL_CLEANUP=1`,
  `HOMEBREW_NO_ENV_HINTS=1`, `NONINTERACTIVE=1`. **Never** `sudo` (brew refuses root);
  `.pkg` casks prompt for sudo themselves, covered by the run-wide sudo keepalive (§1 CLI).
- `install(*pkgs)` → `brew install --formula -y …`.
- `install_cask(*casks)` → `brew install --cask -y --adopt …`. If brew refuses to adopt
  (version mismatch with a hand-installed app), the module is reported
  **`present-unmanaged`** and never overwritten.
- `installed(pkg)` → `brew list --formula --versions`; `cask_installed(c)` →
  `brew list --cask --versions`.
- `upgrade(*pkgs)` → `brew upgrade --formula …` (used by `--update`, see §6).
- `add_repo(BrewTap(name, url=None))` → `brew tap`; `TypeError` for Dnf/Apt repos.
- `refresh_index()` → one best-effort `brew update` per run on macOS.
- Public `pkg.install_cask()` / `pkg.cask_installed()` — opt-in by name, `UnsupportedOS`
  off macOS (mirrors `install_aur`).
- `manager_for()` → `Brew()` for family `macos`. `Source` admits `BrewTap`.

### `exec/primitives/launchd.py` (new)
- `user_agent(ctx, label, program_args, *, start_interval=None, start_calendar=None,
  run_at_load=False, env=None)` — writes `~/Library/LaunchAgents/<label>.plist` via
  `plistlib`; on change `launchctl bootout gui/<uid>/<label>` (ignore not-loaded) then
  `launchctl bootstrap gui/<uid> <plist>`. Idempotent.
- `system_daemon(...)` — same shape for `/Library/LaunchDaemons` (root; used by
  `macos-limits`).
- `agent_loaded(ctx, label)`, `remove_agent(ctx, label)`. Labels `dev.devboost.<name>`.

### Module contract additions
- `PackageModule`: `brew_pkg: str | None` (None → `name`), `brew_cask: str | None`. On
  macOS verify uses `Brew.installed`/`cask_installed`, not `which` (Apple's stock tools
  would otherwise satisfy verify).
- `FlatpakApp`: `cask: str | None`; macOS branch installs/verifies the cask; missing
  `cask` on macOS → `UnsupportedOS` naming the module.
- **Custom-install modules** (own `install()` that bypasses `pkg.install`) get an explicit
  `per_os.macos` strategy — the fields above do not reach them. Full list in §2.
- Ordering: `PackageModule`, `FlatpakApp` and every module whose macOS strategy uses brew
  add `Homebrew` to `requires`; `Homebrew` is `families=("macos",)`, so Linux plans drop it
  (as `Flatpak` is dropped on Arch — `core/plan.py`).
- `provided_by=("macos",)` → `provided-by-macos`; `families` drops Linux-only modules.

### Errors
- `InstallError(tool, exact_command, code)` for brew/launchctl/xcodes/tmutil failures.
- New `NeedsUser(reason, how_to_fix)` → reported `blocked` (not `fail`); plan continues.
  Raised for: Xcode without Apple ID auth, `mkcert -install` without a prompt, OrbStack /
  Docker Desktop first-launch license screens, Tailscale network-extension approval,
  `chezmoi-repo` with no repo configured.

### CLI
- `_DEFAULT_PROFILE["macos"] = "macos"`.
- On macOS: refuse to run as root (explain); `installer`, `accounts`, `brain` →
  `UnsupportedOS("<cmd> is Linux-only")`.
- **Sudo once:** at run start on macOS, if the plan contains any sudo-needing step,
  `sudo -v` once and refresh it in a background thread every 60 s until exit.
- **No sleep:** the run re-execs itself under `caffeinate -dimsu` on macOS.
- New commands: `devboost docker use <runtime>` (§4); `devboost revert macos-defaults
  [key…]` (§2); `devboost secrets import-key` (§5).

## 2. Catalog mapping

### Formulae (brew name = module name unless noted)
git, wget, jq, htop, fd, fzf, tmux, eza, bat, btop, zoxide, atuin, direnv,
**delta → `git-delta`**, lazygit, lazydocker, dust, duf, sd, yq, tealdeer, fastfetch, gh,
coreutils, ripgrep, mosh, starship, chezmoi, uv, mise, neovim, age, smartmontools, restic,
**ffmpeg-full → `ffmpeg`**, **fresh → `fresh-editor`**, **glow** (new), **bash** (new,
tool only), **zsh-autosuggestions** + **zsh-syntax-highlighting** (module `zsh-plugins`,
`families=("macos",)` since zsh is the shell only on macOS; sourced by `shell.zsh`), **duti**, **xcodes**
(homebrew-core), **mkcert**. ddev via `BrewTap("ddev/ddev")` → `ddev/ddev/ddev`.

### Casks
| Module | Cask |
|---|---|
| obsidian / bruno / bitwarden / localsend / vlc | same names |
| jetbrains-toolbox (opt-in), vscode (opt-in) | `jetbrains-toolbox`, `visual-studio-code` |
| ghostty (default) / wezterm (opt-in) | `ghostty` / `wezterm@nightly` |
| nerd-fonts | `font-jetbrains-mono-nerd-font` (Linux pin v3.2.1; cask tracks latest — accepted) |
| tailscale | `tailscale-app` |
| stats, raycast, alt-tab, thaw, monitorcontrol, betterdisplay, keka | same names |
| aerospace | `nikitabobko/tap/aerospace` (BrewTap) |
| qlmarkdown, syntax-highlight | Quick Look extensions |
| opt-in: maccy, ollama-app, lm-studio, pearcleaner, keycastr, linearmouse, android-studio, expo-orbit, herd | same names |

### `provided_by=("macos",)`
curl (brew curl is keg-only), unzip, wl-clipboard (pbcopy/pbpaste), flameshot (⌘⇧5; brew
cask deprecated), fwupd, thermald, power-profiles-daemon, dnf-automatic-security, codecs,
va-hwaccel, openh264.

### `families` = Linux only
rpmfusion, dnf-tune, fedora-third-party, flatpak, gearlever, gnome-*, hardware/NVIDIA,
snapper, snapper-dnf-hook, grub-btrfs, btrfs-assistant, btrfsmaintenance, swapfile, zram,
earlyoom, gpu-detect, server-firewall, bash-config, caddy, code-server, browser-view,
crossarch-build, orca-*, Ubuntu multimedia variants, omarchy-update-hook.

### Per-OS strategies (`per_os.macos`) — including custom-install modules
| Module | macOS strategy |
|---|---|
| build-tools | requires `xcode-clt` |
| lazygit, lazydocker, sd | brew formula (today: COPR / curl installer / `linux-gnu` asset + `grep -P` + BSD-incompatible `install -D`) |
| herdr | catalog pin for `herdr-macos-aarch64`; replace `install -D` with `mkdir -p` + `install -m` (BSD-safe) |
| nerd-fonts | cask; verify cask (not `fc-list`) |
| wezterm | cask `wezterm@nightly`; skip `.desktop`/icons |
| ghostty | cask; verify cask (no binary on PATH) |
| vscode, jetbrains-toolbox | cask |
| dotnet-sdk | Microsoft `dotnet-install.sh --channel 10.0 --install-dir ~/.dotnet` (no sudo; same pin as Linux; verify `~/.dotnet/dotnet --list-sdks` has `10.`) |
| android-sdk | cask `android-commandlinetools`; `ANDROID_HOME=~/Library/Android/sdk` via `env.sh` (not `/etc/profile.d`) |
| tailscale | cask `tailscale-app`; symlink `/Applications/Tailscale.app/Contents/MacOS/Tailscale` → `~/.local/bin/tailscale`; no `--ssh` (Mac is a fleet client); extension approval → `NeedsUser` |
| playwright | skip the dnf system-deps step |
| ddev | BrewTap + formula; `mkcert -install` |
| docker, docker-build-gc | `DockerRuntime` (§4) |
| aspire-gc, restic-backup, restic-b2, obsidian-sync, browser-mcp | `launchd.user_agent` (same schedules); restic path resolved via `which` (not `/usr/bin/restic`) |
| ssh-setup | no longer requires an age bundle: PAT via `gh auth token`; key file + `UseKeychain yes` + `ssh-add --apple-use-keychain` |
| chezmoi-repo | `chezmoi init --apply --force` (also fixes a Linux tty hang); no repo configured → `NeedsUser` |
| claude-notify | ntfy **and** a native notification (`osascript -e 'display notification …'`) on Darwin |
| secrets | gh-first (`gh auth setup-git`, keychain); age bundle optional (§5) |

### New macOS-only modules (`families=("macos",)`)
| Module | Install | Verify |
|---|---|---|
| `xcode-clt` | `softwareupdate` silent CLT install | `xcode-select -p` |
| `homebrew` (requires xcode-clt) | official installer, `NONINTERACTIVE=1`; `brew analytics off` | brew exists and analytics off |
| `rosetta` | `softwareupdate --install-rosetta --agree-to-license` | `pgrep oahd` / `arch -x86_64 true` |
| `macos-defaults` | table below; snapshot prior values first; restart Dock/Finder/SystemUIServer only on change | all keys read back equal |
| `macos-limits` | LaunchDaemon `launchctl limit maxfiles 524288 524288`; `ulimit -n` in `shell.zsh` | `launchctl limit maxfiles` |
| `macos-firewall` | `socketfilterfw --setglobalstate on` (sudo) | `--getglobalstate` enabled |
| `timemachine-exclusions` | `tmutil addexclusion` for `~/Library/Caches`, `~/.colima`, `~/.gradle`, `~/.npm`, `~/.cache`, `~/.nuget/packages`, `~/Library/Developer/Xcode/DerivedData`; `node_modules`/`vendor` via sticky exclusions from a login agent sweep of `~/repos` | `tmutil isexcluded` |
| `stats`, `raycast`, `aerospace`, `alt-tab`, `thaw`, `monitorcontrol`, `betterdisplay`, `keka` | casks | cask installed |
| `quicklook` | `qlmarkdown`, `syntax-highlight` | casks installed |
| `default-apps` | `duti` table: code/text extensions → Zed (`dev.zed.Zed`) | `duti -x <ext>` |
| `aerospace-config`, `ghostty` keybinds | via dotfiles (§3) | — |
| `xcode` (opt-in `ios`) | `xcodes install <pin> --select --experimental-unxip --empty-trash`; `sudo xcodebuild -license accept`; `-runFirstLaunch` | `xcodes installed <pin>` + selected |
| `ios-tooling` (opt-in `ios`) | brew `cocoapods`, `watchman`; `xcodes runtimes install "iOS <pin>"` | `pod`, `watchman`, `xcrun simctl list runtimes` |
| `zsh-config` | marker check (dotfiles own `~/.zshrc`) | marker + sources `shell.zsh` |

**Opt-in cross-OS module:** `android-emulator` — emulator + system image (`arm64-v8a` on
aarch64, `x86_64` on x86_64) + one Pixel AVD.

**Pins** for `xcode` / `ios-tooling` (Xcode version, iOS runtime) live in `catalog.toml`
next to herdr's pins, set to the newest stable GA at implementation time (Xcode 27 / iOS 27 as of 2026-09).
(`devboost.lock` holds only module names, so it cannot carry versions.)

Xcode auth: `XCODES_USERNAME`/`XCODES_PASSWORD` env or an existing xcodes keychain
session; else `NeedsUser`.

#### `macos-defaults` table
| Domain / key | Value |
|---|---|
| `NSGlobalDomain KeyRepeat` / `InitialKeyRepeat` | `2` / `15` |
| `NSGlobalDomain ApplePressAndHoldEnabled` | `false` |
| `NSGlobalDomain AppleShowAllExtensions` | `true` |
| `NSGlobalDomain NSAutomaticSpellingCorrectionEnabled` / `NSAutomaticQuoteSubstitutionEnabled` / `NSAutomaticDashSubstitutionEnabled` | `false` |
| `com.apple.finder AppleShowAllFiles` / `ShowPathbar` / `ShowStatusBar` | `true` |
| `com.apple.finder FXPreferredViewStyle` | `Nlsv` |
| `com.apple.desktopservices DSDontWriteNetworkStores` / `DSDontWriteUSBStores` | `true` |
| `com.apple.dock autohide` / `tilesize` / `show-recents` | `true` / `48` / `false` |
| `com.apple.screencapture target` / `type` | `clipboard` / `png` — screenshots land on the clipboard, ready for `herdr --remote` Ctrl+V image paste; ⌘⇧5 “Save to” for files |
| `com.apple.AppleMultitouchTrackpad Clicking` | `true` |

Typed values (`-bool`/`-int`/`-string`). Before the first write, prior values (or
"absent") are saved to `~/.local/state/devboost/macos-defaults.prev.json`;
`devboost revert macos-defaults [key…]` restores them.

### Profiles (`profiles.toml`)
- `base` += `homebrew`, `xcode-clt`, `rosetta`, `pass`, `pass-store` (pass per companion spec).
- `cli` += `herdr-plugins`, `glow` (**every OS**).
- `shell` += `zsh-config`, `zsh-plugins`; `terminal` += `zsh-config`.
- `shell` and `terminal`: `wezterm` → `ghostty` (**every OS**). `wezterm` moves to a new
  opt-in profile `optional-terminals` and is marked deprecated in the docs.
- `editors` = `zed`, `fresh`, `fresh-lsp` (Zed spec); `optional-editors` += `vscode`.
- New `ios` = `xcode`, `ios-tooling`.
- New `macos-desktop` = `macos-defaults`, `macos-limits`, `macos-firewall`,
  `timemachine-exclusions`, `stats`, `raycast`, `aerospace`, `alt-tab`, `thaw`,
  `monitorcontrol`, `betterdisplay`, `keka`, `quicklook`, `default-apps`.
- New `macos-extras` (opt-in) = `maccy`, `ollama-app`, `lm-studio`, `pearcleaner`,
  `keycastr`, `linearmouse`, `android-studio`, `expo-orbit`, `herd`, `wezterm`.
- New `macos` = `base`, `cli`, `shell`, `editors`, `python`, `web`, `laravel`, `dotnet`,
  `data`, `devops`, `react-native`, `apps`, `macos-desktop`, `dev-hygiene`, `remote`,
  `claude`, `codex`, `pi` (Linux-only members fall out via `families`).
- README tables regenerated.

## 3. Shell, terminal & dotfiles

```
dotfiles/
  dot_config/devboost/
    env.sh        NEW POSIX: PATH (~/.local/bin, ~/.dotnet/tools, $ANDROID_HOME/platform-tools),
                      RIPGREP_CONFIG_PATH, VISUAL/EDITOR (Zed spec), Darwin: LANG=en_US.UTF-8,
                      XDG_CONFIG_HOME=$HOME/.config, ANDROID_HOME=~/Library/Android/sdk
    aliases.sh    NEW POSIX aliases/functions (moved out of shell.bash)
    shell.bash        env.sh + aliases.sh; shopt, bash-preexec, inits
    shell.zsh     NEW env.sh + aliases.sh; zsh-only parts
  dot_zprofile.tmpl   NEW (darwin): brew shellenv; `mise activate zsh --shims` (GUI apps/IDEs)
  dot_zshrc.tmpl      NEW (darwin): loader → shell.zsh; then `[[ -r ~/.zshrc.local ]] && source ~/.zshrc.local`
  dot_bash_profile.tmpl NEW (darwin): sources env.sh (so `bash -lc` launchers get PATH)
```

- `shell.zsh`: history (`HISTSIZE`/`SAVEHIST`, `share_history`, `hist_ignore_all_dups`);
  brew `site-functions` on `fpath` + `compinit`; `source <(fzf --zsh)` **before** atuin;
  `mise activate zsh`, `starship init zsh`, `atuin init zsh`, `zoxide init zsh`,
  `direnv hook zsh`; zsh-syntax-highlighting then zsh-autosuggestions (load order per
  upstream); `ulimit -n 524288`.
- `shell.bash`: `eval "$(fzf --bash)"` **only if** `fzf --bash` is supported (fzf ≥ 0.48);
  otherwise the existing `/usr/share/fzf/...` paths (Ubuntu 24.04 ships 0.44).
- **Existing `~/.zshrc`:** first apply backs it up to `~/.zshrc.pre-devboost`; the
  managed file sources `~/.zshrc.local` for machine-specific/installer lines.
- `LANG=en_US.UTF-8` on Darwin — otherwise macOS sends `LC_CTYPE=UTF-8` over ssh/mosh,
  which Linux rejects and mosh refuses.
- Brew `bash` 5 is installed as a tool (not login shell) so `#!/usr/bin/env bash` scripts
  and `bash -lc` MCP launchers get a modern bash.
- **Portable scripts:** tmux `resources.sh`, wezterm `status.lua`, Claude `statusline.sh`
  read RAM/disk via `sysctl hw.memsize` / `vm_stat` / `df -g` on Darwin (today `/proc` +
  `df -BG`); `starship.toml` switches to starship's built-in `memory_usage` module;
  `pw-autoregister.sh` uses `gtimeout` when `timeout` is absent.
- **Terminal (every OS): Ghostty.** Why: WezTerm's last stable is Feb 2024 (nightlies
  only) and its multiplexer is redundant with herdr; Ghostty 1.3 is actively maintained,
  fastest on macOS, native on both OSes, and has everything agent work needs (kitty
  keyboard protocol → Shift+Enter, OSC 52, synchronized output, kitty graphics,
  `notify-on-command-finish`). Linux install: the existing `ghostty` module's Fedora/Ubuntu
  strategies (unchanged); Omarchy keeps foot (`provided_by=("omarchy",)`).
  Ghostty config sets `notify-on-command-finish = unfocused`.
- **Image paste is herdr's, not the terminal's:** `herdr --remote` reads the local
  clipboard image (Linux `wl-paste`, macOS `osascript` PNG), ships it over its SSH
  connection, stages it in the remote's `$TMPDIR/herdr-clipboard-images-<uid>/` and pastes
  the path. Trigger: `keys.remote_image_paste = "ctrl+v"` or an empty bracketed paste.
  Therefore **no terminal config may bind Ctrl+V** (WezTerm's `paste.lua` smart paste is
  retired with WezTerm; `img2ssh` is not ported).
- **Keyboard:** Ghostty `macos-option-as-alt = left` (and WezTerm equivalent) — right
  Option keeps accents. Ghostty/WezTerm on Darwin add **Cmd** equivalents of every
  Ctrl+Shift binding (both work). WezTerm leader on Darwin → `Ctrl+A` (macOS keeps
  Ctrl+Space for input-source switching). Ghostty `shell-integration = detect`.
- **AeroSpace** config (`~/.config/aerospace/aerospace.toml`) via chezmoi: workspaces 1–9
  on Ctrl+Alt+digit, focus Ctrl+Alt+hjkl, move Ctrl+Alt+Shift+hjkl, layout toggles.
  Deliberately **not** plain Alt: AeroSpace hotkeys are global and would swallow
  wezterm's Alt+hjkl pane keys and readline/fzf Alt bindings in the terminal.
- `.chezmoiignore`: Omarchy guard → `{{ if and (eq .chezmoi.os "linux") (eq
  .chezmoi.osRelease.id "omarchy") }}` (default `missingkey=error` + no `osRelease` on
  Darwin would fail every Mac apply). Darwin ignores `.bashrc`, `.bash-preexec.sh`,
  `.config/systemd`, `.config/caddy`; Linux ignores `.zshrc`, `.zprofile`,
  `.bash_profile`, `.config/aerospace`.

## 4. Docker runtimes

`modules/_docker_runtime.py`: `DockerRuntime` protocol — `install`, `configure`, `start`,
`stop`, `disable_autostart`, `verify`, `daemon_config_path`, `context_name`.

| Concern | Colima (default) | OrbStack | Docker Desktop |
|---|---|---|---|
| Install | brew `colima`, `docker`, `docker-compose`, `docker-buildx`; `cliPluginsExtraDirs` in `~/.docker/config.json` | cask `orbstack` | cask `docker-desktop` |
| Resources | `colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu C --memory M --disk 100` | `orb config set` | `settings-store.json` |
| Autostart | `brew services start colima` | login item | auto-start setting |
| Context | `colima` | `orbstack` | `desktop-linux` |
| `/var/run/docker.sock` | `sudo ln -sf ~/.colima/default/docker.sock /var/run/docker.sock` | managed | managed |
| Daemon config | `docker:` in `~/.colima/default/colima.yaml` + restart | `~/.orbstack/config/docker.json` + `orb restart docker` | Docker Desktop `daemon.json` |

Colima sizing `C = max(2, ncpu // 2)`, `M = max(4, ram_gib // 4)` GiB (this Mac: 5 CPU,
6 GiB). **Selection:** `DEVBOOST_DOCKER_RUNTIME` > `docker_runtime` in
`~/.config/devboost/config.toml` > `colima`; `Settings.docker_runtime:
Literal["colima","orbstack","docker-desktop"]`. **Verify:** `docker info` succeeds on the
selected runtime's context.

**`devboost docker use <runtime>`:** (1) warn that images/volumes/ddev DBs live in each
runtime's VM, offer `ddev snapshot --all`; (2) `ddev poweroff`; (3) stop old runtime +
disable its autostart (not uninstalled); (4) install/configure/start new; switch context,
socket, daemon config; (5) persist choice; re-verify `docker`, `docker-build-gc`,
`aspire-gc`, `ddev`, `data-services`. (`data-services` images — postgres 18, valkey 8.1,
dbgate — are multi-arch.)

## 5. Secrets on macOS

- **GitHub:** `gh auth setup-git` (token stays in keychain; never `~/.git-credentials`
  plain text). If `gh` is not logged in: `gh auth login` once via `/dev/tty`.
- **Age bundle (optional):** bootstrap secrets (ntfy, restic/B2, …). Key stored in the
  macOS keychain (`security add-generic-password -s devboost-age`) via
  `devboost secrets import-key`; file/env remain fallbacks.
- **pass:** default on every OS with per-device keys and auto-sync — see the
  [pass companion spec](2026-09-18-pass-multi-device-design.md). macOS part here: brew
  `pass`, `gnupg`, `pinentry-mac`; `gpg-agent.conf` `pinentry-program
  /opt/homebrew/bin/pinentry-mac` (passphrase cached in the login keychain).
- **SSH:** key file + keychain (`UseKeychain yes`); no Bitwarden agent.

## 6. Updates

`devboost install --update` on macOS runs `brew upgrade --formula` for the plan's
formulae. Casks with `auto_updates` (VS Code, Obsidian, Ghostty, Raycast, …) update
themselves — no `--greedy`. No background upgrades. `softwareupdate` is never automatic.

## 7. Delivery

- Artifact `devboost-darwin-arm64` (PyInstaller onefile, ad-hoc signed by default; curl
  sets no quarantine). Linux asset names unchanged; no Ventoy tarball on Darwin.
- `release.yml`: matrix `{runner: macos-15, arch: darwin-arm64}` (pinned; a binary built on
  15 runs on 26/27); tag check
  `grep -oP` → `sed -nE`; checks job also on `macos-15`; combine step adds the Mac binary
  to `checksums.txt`.
- `build-bundle.sh`: `Darwin/arm64 → darwin-arm64`; `shasum -a 256` fallback; skip
  Ventoy tarball; smoke `devboost --version && devboost list macos`.
- `get.sh`: Darwin → `darwin-arm64` (refuse Intel and macOS < 15; warn on 15); `gs_macos_prereqs` (CLT silent,
  Homebrew `NONINTERACTIVE=1`, brew shellenv); skip Ventoy archive; `exec … </dev/tty`
  so prompts work under `curl|bash`; PATH hint names `~/.zshrc`. Default profile stays
  `terminal` on every OS; README shows `… | bash -s -- macos`.
- `core/selfupdate.py`: `_arch()` → `darwin-arm64`; **skip the tarball download/verify on
  Darwin**.

## 8. Doctor on macOS

Replaces the fedoraproject.org probe with: brew present, CLT present, Rosetta, disk space
on `/`, FileVault on (warn), firewall on, SIP enabled (warn), Time Machine configured
(warn), iCloud "Desktop & Documents" sync (warn — repos/`node_modules` churn), battery
charge limit hint (26.4+, manual), selected Docker runtime healthy, `present-unmanaged`
apps, pass enrollment status (companion spec), Raycast/Maccy hotkey hints.

## 9. Testing

All via `FakeExecutor`; no real brew in CI.
- `osinfo`: Darwin detect, `arm64→aarch64`, `OsMap.macos` precedence, headless local/SSH.
- `pkg.Brew`: argv + env, never sudo, `--adopt` + `present-unmanaged`, `BrewTap`,
  `upgrade`, `install_cask` raises off macOS.
- `launchd`: plist equality (`plistlib`), bootstrap idempotency, daemon vs agent.
- **Catalog contract test:** for `OsInfo(distro="macos", family="macos", arch="aarch64")`,
  every module in expanded `macos` + `macos-extras` + `ios` resolves (brew / cask /
  `per_os.macos` / cross-platform) or is `families`-dropped or `provided_by`. xfail
  allow-list empties by M5.
- `DockerRuntime`: per-runtime argv; switch path incl. snapshot prompt; selection
  precedence.
- `macos-defaults`: typed argv, snapshot/revert, restart-only-on-change.
- Dotfiles: `.chezmoiignore` rendered for darwin / linux / omarchy (`chezmoi
  execute-template`, skip if absent); `zsh -n shell.zsh`; `bash -n shell.bash`;
  `shellcheck` on portable scripts.
- CI: checks on `ubuntu-22.04` and `macos-15` (blocking), plus GitHub's `xcode-27` image —
  which runs **macOS 27** (public preview; GitHub now names macOS images by Xcode
  version) — as a non-blocking job until it leaves preview.
- **E2E:** `scripts/vm-test-macos.sh` for **macOS 27 and 26** (tart: `tart clone
  ghcr.io/cirruslabs/macos-<name>-base`, exact 27 image name confirmed at M6; `tart run --no-graphics`, ssh `admin@$(tart ip)`,
  snapshot = clone of stopped VM; verbs `create/snapshot/revert/list/destroy`, mirroring
  `vm-test.sh`). Rehearse in tart, then run on the real Mac. Shared-shell changes also
  run Fedora + Ubuntu `vm-test` before merge.

## 10. Documentation

Each milestone PR ships its own docs; a PR is not done without them.

| Doc | Milestone |
|---|---|
| `.specify/memory/constitution.md` → v3.1.0: Principle VI "Fedora is the reference Linux; macOS is a first-class family" | M1 |
| `docs/architecture.md`, `docs/adding-a-module.md` (brew/cask/`per_os.macos`, contract test) | M1 |
| `docs/credentials.md` (gh-first, keychain age key) | M1 |
| `docs/macos.md` (backend, profiles, dropped/provided, one-time manual steps, troubleshooting) | M2→M6 (grows) |
| `docs/docker-runtimes.md` (incl. licensing) | M4 |
| `docs/macos-primer.md` (new-to-Mac cheat sheet for this setup) | M5 |
| `docs/vm-testing.md` (tart), `docs/maintenance.md`, `docs/recovery-runbook.md`, `docs/remote-fleet.md` (Mac client), `docs/agents.md` (herdr plugins default) | M3–M6 |
| `README.md` (macOS install, regenerated tables), `CLAUDE.md` (mission), `CHANGELOG.md` | every PR / M6 |

## 11. Rollout (one PR each)

| # | Milestone | Outcome |
|---|---|---|
| M1 | Engine core: `OsMap.macos`, arch normalize, executor PATH, `Brew` (+adopt/upgrade/tap), `launchd`, `NeedsUser`, root guard, sudo keepalive, caffeinate, `secrets` gh-first + keychain age key, contract test (xfail list), constitution v3.1.0 | engine runs on Darwin |
| M2 | Shell & dotfiles: env/aliases split, `shell.zsh`, zprofile/zshrc/bash_profile, `.chezmoiignore` fix, portable scripts, fzf fallback, Option-as-Alt + Cmd bindings, `zsh-config`, zsh plugins | `devboost install terminal` from the clone |
| M3 | Catalog: formulae/casks, custom-install `per_os.macos`, provided_by/families sweep, `xcode-clt`, `homebrew`, `rosetta`, herdr pins + `herdr-plugins`/`glow` default, `macos` profile | most of the workstation |
| M4 | Docker runtimes + `devboost docker use`; launchd timers (aspire-gc, build-gc, restic, obsidian-sync, browser-mcp) | ddev, Aspire, data-services |
| M5 | Desktop: `macos-defaults` (+revert), limits, firewall, Time Machine exclusions, casks (Raycast, AeroSpace + config, AltTab, Thaw, monitor tools, Keka, Stats, Quick Look), `default-apps`; opt-in `ios`, `macos-extras`, `android-emulator`; primer | full desktop + iOS |
| M6 | Delivery: darwin binary, `get.sh`, self-update, CI matrix, tart `vm-test-macos.sh`, final docs | fresh Mac via `curl … \| bash` |

## Out of scope

Intel Macs; Homebrew tap distribution; `brew bundle` batching; Karabiner; Mac as a brain
host or USB builder; notarization with a Developer ID; managing the Time Machine
destination disk; FileVault enablement (warn only); the battery charge limit (manual, doctor hint).
