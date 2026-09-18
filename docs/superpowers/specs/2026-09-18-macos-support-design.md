# macOS support — design

**Date:** 2026-09-18 · **Status:** approved (brainstorm) · **Branch:** `feat/macos-support`

## Goal

Make an Apple Silicon Mac a **primary dev-boost workstation**: `curl … | bash` (or
`devboost install` with no args) on a fresh Mac yields the same "builds out of the box"
promise as Fedora — Laravel (ddev), .NET + Aspire, Python (uv), web, React Native
(Android **and iOS**), editors, GUI apps, Claude/Codex — with zsh, chezmoi dotfiles, and a
macOS-native desktop layer. Modeled on the Omarchy/Arch backend (v0.1.80): one catalog,
per-OS divergence as typed data, no engine branching.

## Decisions (from brainstorm)

| Topic | Decision |
|---|---|
| Role | Primary workstation; full parity where it makes sense |
| Architecture | `macos` is a first-class family (Approach 1). `brew bundle` batching is a later optimisation; the data model keeps it possible |
| Hardware | Apple Silicon only (`darwin-arm64`). Intel Macs are refused with a clear message |
| Shell | zsh on macOS, bash on Linux; shared POSIX core |
| Docker | Three switchable runtimes — **Colima (default)**, OrbStack, Docker Desktop — full reconfigure on switch |
| Desktop | `macos-defaults` (`defaults write`) + **Stats** (menu-bar vitals). No tiling WM / Karabiner / launcher |
| iOS | Full Xcode via `xcodes` + iOS simulator runtime + CocoaPods/watchman |
| Delivery | `get.sh` + frozen `devboost-darwin-arm64` binary (no Homebrew tap) |

### Why Colima is the default (licensing)

The Mac is used for employer and client work. OrbStack's Free plan is limited to personal,
non-commercial use; freelance/employer/business use or >$10k/yr related income requires Pro
($8/user/mo) — see <https://docs.orbstack.dev/licensing>. Docker Desktop is free only for
organisations with <250 employees **and** <$10M revenue (the test applies to the org the
work is for). Colima is MIT — free for any use — and ddev officially supports it; with
ddev's default Mutagen sync its performance is on par with OrbStack. OrbStack and Docker
Desktop remain one command away (`devboost docker use …`).

## 1. Engine core

### `core/osinfo.py`
- `OsMap` gains `macos: T | None = None`; `get()` includes it in the distro/family lookup.
- `detect()` on Darwin fills `version_id` from `sw_vers -productVersion`.
- `is_headless()` on Darwin: `False` unless the process is in an SSH session
  (`SSH_CONNECTION`/`SSH_TTY` set). The current systemd-default-target fallback would mark
  every Mac headless and silently skip all GUI modules.

### `exec/primitives/pkg.py` — `Brew`
- Brew binary resolved once as `/opt/homebrew/bin/brew` (fallback: `which brew`), not from
  PATH — a fresh `curl|bash` run has no brew shellenv.
- Environment on every call: `HOMEBREW_NO_AUTO_UPDATE=1`, `HOMEBREW_NO_INSTALL_CLEANUP=1`,
  `HOMEBREW_NO_ENV_HINTS=1`, `NONINTERACTIVE=1`.
- `install(*pkgs)` → `brew install --formula -y …`; `install_cask(*casks)` →
  `brew install --cask -y …`. **Never** `sudo` (brew refuses root).
- `installed(pkg)` → `brew list --formula --versions <pkg>`;
  `cask_installed(c)` → `brew list --cask --versions <c>`.
- `add_repo(repo)` accepts a new typed source `BrewTap(name: str, url: str | None = None)`
  → `brew tap <name> [url]`; raises `TypeError` for Dnf/Apt repos.
- `refresh_index()` → one best-effort `brew update` per run on the `macos` family.
- Public `pkg.install_cask(ctx, *casks)` mirrors `install_aur`: opt-in by name, raises
  `UnsupportedOS` off macOS. `pkg.cask_installed(ctx, cask)` likewise.
- `manager_for()` returns `Brew()` for family `macos`.
- `Source` becomes `OsMap[DnfRepo | AptRepo | BrewTap]` (and `Script` where already allowed).

### `exec/primitives/launchd.py` (new; counterpart of `systemd.py`)
- `user_agent(ctx, label, program_args, *, start_interval: int | None = None,
  start_calendar: dict[str, int] | None = None, run_at_load: bool = False,
  env: dict[str, str] | None = None)` — writes `~/Library/LaunchAgents/<label>.plist`
  via stdlib `plistlib`; if content changed, `launchctl bootout gui/<uid>/<label>` (ignore
  "not loaded") then `launchctl bootstrap gui/<uid> <plist>`. Idempotent.
- `agent_loaded(ctx, label) -> bool` — `launchctl print gui/<uid>/<label>` succeeds.
- `remove_agent(ctx, label)` — bootout + delete plist (used by runtime switching).
- Labels are namespaced `dev.devboost.<name>`.

### Module contract additions (`model.py` / bases)
- `PackageModule`: `brew_pkg: str | None = None` (None → module `name`),
  `brew_cask: str | None = None`. On macOS, **verify uses `Brew.installed`/`cask_installed`,
  not `which`** — otherwise Apple's stock `git`/`curl` would satisfy verify.
- `FlatpakApp`: `cask: str | None = None`; macOS branch installs/verifies the cask; a
  subclass with no `cask` on macOS raises `UnsupportedOS` naming the module.
- Ordering: `PackageModule` and `FlatpakApp` add `Homebrew` to `requires`, as do any
  modules whose macOS strategy calls brew. `Homebrew` is `families=("macos",)`, so on Linux
  the plan drops it the same way it drops `Flatpak` on Arch. No graph changes needed.
- `provided_by=("macos",)` reports `provided-by-macos`; `families` drops Linux-only modules
  (dropped `requires` are already filtered — `core/plan.py`).

### CLI
- `_DEFAULT_PROFILE["macos"] = "macos"` (`cli/app.py`).
- `installer`, `accounts`, `brain` raise `UnsupportedOS("<cmd> is Linux-only")` on macOS.
- New `devboost docker use <colima|orbstack|docker-desktop>` (section 4).
- Running devboost as root on macOS is refused (brew cannot run as root); individual
  root-needing steps use `sudo` per command.

## 2. Catalog mapping

### Formulae (brew name = module name unless noted)
git, curl, wget, jq, htop, fd, fzf, tmux, eza, bat, btop, zoxide, atuin, direnv,
**delta → `git-delta`**, lazygit, lazydocker, dust, duf, sd, yq, tealdeer, fastfetch, gh,
coreutils, ripgrep, mosh, starship, chezmoi, uv, neovim, pass, smartmontools, age (for
`secrets`), **ffmpeg-full → `ffmpeg`**.

### Casks
| Module | Cask |
|---|---|
| obsidian / bruno / bitwarden / localsend / vlc | `obsidian` / `bruno` / `bitwarden` / `localsend` / `vlc` |
| vscode | `visual-studio-code` |
| jetbrains-toolbox | `jetbrains-toolbox` |
| wezterm / ghostty | `wezterm` / `ghostty` |
| nerd-fonts | the `font-*-nerd-font` casks matching the Linux font set |
| tailscale | `tailscale-app` |
| dotnet-sdk | `dotnet-sdk` |
| android-sdk | `android-commandlinetools` (+ JDK via mise as today; `ANDROID_HOME` in `env.sh`) |
| stats (new) | `stats` |

### `provided_by=("macos",)`
unzip, wl-clipboard (pbcopy/pbpaste), flameshot (⌘⇧5), fwupd, thermald,
power-profiles-daemon, dnf-automatic-security (macOS automatic security updates), codecs,
va-hwaccel, openh264 (VideoToolbox).

### `families` = Linux only (dropped on macOS)
rpmfusion, dnf-tune, fedora-third-party, flatpak, gearlever, gnome-* (all), hardware/NVIDIA
(all), snapper, snapper-dnf-hook, grub-btrfs, btrfs-assistant, btrfsmaintenance, swapfile,
zram, earlyoom, gpu-detect, server-firewall, bash-config, brain-host (caddy, code-server,
browser-view, crossarch-build), orca-ide/orca-serve (already scoped), multimedia Ubuntu
variants, omarchy-update-hook.

### Per-OS strategies (`per_os.macos`)
- **build-tools** → requires `xcode-clt`.
- **ddev** → `BrewTap("ddev/ddev")` + `ddev`; then `mkcert -install` (one-time password
  prompt; `NeedsUser` if it cannot prompt).
- **docker** → delegates to the active `DockerRuntime` (section 4).
- **docker-build-gc** → writes the GC policy to the active runtime's daemon config.
- **aspire-gc, restic-backup, restic-b2, obsidian-sync** → `launchd.user_agent` with the same
  schedule as the systemd timers.
- **ssh-setup / secrets / chezmoi-repo** → unchanged logic; `ssh-add --apple-use-keychain`
  and `UseKeychain yes` in the managed ssh config on Darwin.
- **herdr, fresh, codex-code, claude-*, pi-harness, mise, web-runtimes, LSPs, playwright,
  tpm, tmux-persist, agent-sudo** → cross-platform already; implementation verifies each
  picks a Darwin asset / path (herdr's release-asset picker, fresh's installer) and adds a
  `brew_pkg`/per-OS override where it does not.

### New macOS-only modules (`families=("macos",)`)
| Module | Install | Verify |
|---|---|---|
| `xcode-clt` | `softwareupdate` silent CLT install (label from `softwareupdate -l`) | `xcode-select -p` |
| `homebrew` (requires xcode-clt) | official installer, `NONINTERACTIVE=1` | `/opt/homebrew/bin/brew` exists |
| `xcode` | `xcodes install <XCODE_VERSION> --select --experimental-unxip --empty-trash`; `sudo xcodebuild -license accept`; `sudo xcodebuild -runFirstLaunch` | `xcodes installed <XCODE_VERSION>` and `xcode-select -p` points at it |
| `ios-tooling` (requires xcode) | brew `cocoapods`, `watchman`, `xcodes runtimes install "iOS <IOS_RUNTIME>"` | `pod`, `watchman` present and `xcrun simctl list runtimes` contains it |
| `macos-defaults` | `defaults write` table below; `killall Dock Finder SystemUIServer` only if anything changed | every key reads back equal |
| `stats` | cask `stats` | cask installed |
| `zsh-config` (requires dotfiles) | marker check (dotfiles own `~/.zshrc`) | `~/.zshrc` has devboost marker + sources `shell.zsh` |

`XCODE_VERSION` / `IOS_RUNTIME` are module constants pinned to the newest stable GA
release at implementation time and recorded in `devboost.lock`. Xcode auth: `XCODES_USERNAME`
/ `XCODES_PASSWORD` env or an existing xcodes keychain session; otherwise `NeedsUser`.

#### `macos-defaults` table
| Domain / key | Value |
|---|---|
| `NSGlobalDomain KeyRepeat` / `InitialKeyRepeat` | `2` / `15` |
| `NSGlobalDomain ApplePressAndHoldEnabled` | `false` |
| `NSGlobalDomain AppleShowAllExtensions` | `true` |
| `NSGlobalDomain NSAutomaticSpellingCorrectionEnabled` / `NSAutomaticQuoteSubstitutionEnabled` / `NSAutomaticDashSubstitutionEnabled` | `false` |
| `com.apple.finder AppleShowAllFiles` / `ShowPathbar` / `ShowStatusBar` | `true` |
| `com.apple.finder FXPreferredViewStyle` | `Nlsv` (list) |
| `com.apple.desktopservices DSDontWriteNetworkStores` / `DSDontWriteUSBStores` | `true` |
| `com.apple.dock autohide` / `tilesize` / `show-recents` | `true` / `48` / `false` |
| `com.apple.screencapture location` / `type` | `~/Pictures/Screenshots` / `png` |
| `com.apple.AppleMultitouchTrackpad Clicking` | `true` (tap to click) |

Values are typed (`bool`/`int`/`str`) so `defaults write -bool/-int/-string` is exact.

### Profiles (`profiles.toml`)
- New `ios` = `xcode`, `ios-tooling`.
- New `macos-desktop` = `macos-defaults`, `stats`.
- New `macos` = `base`, `cli`, `shell`, `editors`, `python`, `web`, `laravel`, `dotnet`,
  `data`, `devops`, `react-native`, `ios`, `apps`, `macos-desktop`, `dev-hygiene`,
  `remote`, `claude`, `codex`, `pi` (Linux-only members fall out via `families`).
- `shell` gains `zsh-config`; `base` gains `homebrew`, `xcode-clt`.
- README profile table regenerated (`scripts/gen_profiles_table.py`).

## 3. Shell & dotfiles

```
dotfiles/
  dot_config/devboost/
    env.sh        NEW  POSIX: PATH (~/.local/bin, ~/.dotnet/tools, $ANDROID_HOME/platform-tools),
                       RIPGREP_CONFIG_PATH, EDITOR, XDG_CONFIG_HOME=$HOME/.config (Darwin)
    aliases.sh    NEW  POSIX aliases/functions shared by both shells (moved out of shell.bash)
    shell.bash         sources env.sh + aliases.sh; bash-only parts (shopt, bash-preexec, inits)
    shell.zsh     NEW  sources env.sh + aliases.sh; zsh-only parts
  dot_zprofile.tmpl NEW (darwin): eval "$(/opt/homebrew/bin/brew shellenv)"
                                   eval "$(mise activate zsh --shims)"   # GUI apps / IDEs
  dot_zshrc     NEW (darwin): thin loader → ~/.config/devboost/shell.zsh (devboost marker)
```

- `shell.zsh`: history (`HISTSIZE`/`SAVEHIST`, `setopt share_history hist_ignore_all_dups`),
  brew `site-functions` on `fpath` then `compinit`; `source <(fzf --zsh)` **before** atuin
  (atuin owns Ctrl-R); `mise activate zsh`, `starship init zsh`, `atuin init zsh`,
  `zoxide init zsh`, `direnv hook zsh`.
- `shell.bash`: fzf init becomes `eval "$(fzf --bash)"` (replaces hard-coded
  `/usr/share/fzf/...` paths).
- `XDG_CONFIG_HOME` on Darwin makes lazygit (and other XDG-aware tools) read `~/.config`
  instead of `~/Library/Application Support`.
- `.chezmoiignore`:
  - Omarchy guard becomes `{{ if and (eq .chezmoi.os "linux") (eq .chezmoi.osRelease.id "omarchy") }}`
    — chezmoi's default `missingkey=error` plus the absence of `osRelease` on Darwin would
    otherwise fail `chezmoi apply` on every Mac.
  - Darwin ignores `.bashrc`, `.bash-preexec.sh`, `.config/systemd`, `.config/caddy`.
  - Linux ignores `.zshrc`, `.zprofile`.
- `bash-config` → Linux families only; `zsh-config` is its macOS counterpart. No `chsh`
  (zsh is already the login shell).

## 4. Docker runtimes

`modules/_docker_runtime.py`: a `DockerRuntime` protocol with `install`, `configure`,
`start`, `stop`, `disable_autostart`, `verify`, `daemon_config_path`, `context_name`.

| Concern | Colima | OrbStack | Docker Desktop |
|---|---|---|---|
| Install | brew `colima`, `docker`, `docker-compose`, `docker-buildx`; `cliPluginsExtraDirs: ["/opt/homebrew/lib/docker/cli-plugins"]` in `~/.docker/config.json` | cask `orbstack` (own CLI in `/usr/local/bin`) | cask `docker-desktop` (own CLI) |
| Resources | `colima start --vm-type vz --mount-type virtiofs --cpu C --memory M --disk 100` | `orb config set` cpu / memory_mib | `settings-store.json` |
| Autostart | `brew services start colima` | OrbStack login item | Docker Desktop auto-start setting |
| Context | `colima` | `orbstack` | `desktop-linux` |
| `/var/run/docker.sock` | `sudo ln -sf ~/.colima/default/docker.sock /var/run/docker.sock` | managed by OrbStack | managed by Docker Desktop |
| Daemon config | `docker:` block in `~/.colima/default/colima.yaml` (then restart) | `~/.orbstack/config/docker.json` + `orb restart docker` | Docker Desktop `daemon.json` |

Colima sizing: `C = max(2, ncpu // 2)`, `M = max(4, ram_gib // 4)` GiB.

**Selection:** `DEVBOOST_DOCKER_RUNTIME` env > `docker_runtime` in
`~/.config/devboost/config.toml` > default `colima`. New `Settings.docker_runtime:
Literal["colima", "orbstack", "docker-desktop"]`.

**Verify (docker module on macOS):** `docker info` succeeds against the selected runtime's
context — any healthy selected runtime passes; dev-boost never fights a runtime the user set up.

**`devboost docker use <runtime>`:**
1. Warn that images/volumes/ddev databases live inside each runtime's VM; offer
   `ddev snapshot --all` (default yes when ddev projects exist).
2. `ddev poweroff`.
3. Stop the old runtime + disable its autostart (**not** uninstalled — switching back is instant).
4. Install/configure/start the new runtime; switch docker context, socket symlink, daemon config.
5. Persist the choice to `config.toml`; re-run verify for `docker`, `docker-build-gc`,
   `aspire-gc`, `ddev`, `data-services`.

## 5. Delivery

- Artifact `devboost-darwin-arm64` (PyInstaller onefile; PyInstaller ad-hoc signs by
  default — sufficient on Apple Silicon; curl sets no quarantine xattr). Linux asset names
  unchanged. No Ventoy tarball on Darwin.
- `release.yml`: matrix entry `{runner: macos-15, arch: darwin-arm64}` (pinned, not
  `macos-latest`); tag-check step switches `grep -oP` → `sed -nE` (BSD-safe); checks job
  also runs ruff + mypy + pytest on `macos-15`; combine step adds the Mac binary to
  `checksums.txt`.
- `build-bundle.sh`: `Darwin/arm64 → darwin-arm64`; `shasum -a 256` fallback; skip Ventoy
  tarball on Darwin; smoke `devboost --version && devboost list macos`.
- `get.sh`: `gs_arch` → `darwin-arm64` on Darwin (refuse Intel); `gs_macos_prereqs` before
  download: Xcode CLT (silent `softwareupdate`), Homebrew (`NONINTERACTIVE=1`, one sudo
  prompt), `eval "$(/opt/homebrew/bin/brew shellenv)"`; skip Ventoy archive; PATH hint
  names `~/.zshrc`. Default profile arg stays `terminal`.
- `core/selfupdate.py`: `_arch()` → `darwin-arm64` on Darwin.

## 6. Error handling

- brew/launchctl/xcodes failures → `InstallError(tool, exact_command, code)`.
- New `NeedsUser(reason, how_to_fix)` → reported as `blocked` (not `fail`); the plan
  continues. Raised for: Xcode without Apple ID credentials, `mkcert -install` without a
  usable prompt, first-launch license screens of OrbStack/Docker Desktop.
- Root invocation on macOS refused up front with an explanation.

## 7. Testing

All via `FakeExecutor`; no real brew in CI.
- `osinfo`: Darwin detect + `sw_vers`; `OsMap.macos` precedence; `is_headless` local vs SSH.
- `pkg.Brew`: exact argv + env, never sudo, `installed`/`cask_installed`, `BrewTap`,
  `install_cask` raises off macOS, `refresh_index` on macOS.
- `launchd`: plist equality via `plistlib`, bootstrap idempotency, `agent_loaded`, `remove_agent`.
- **Catalog contract test**: for `OsInfo(distro="macos", family="macos")` every module in
  the expanded `macos` profile is resolvable (brew name / cask / `per_os.macos` /
  cross-platform) **or** dropped by `families` **or** `provided_by`. An xfail allow-list
  shrinks to empty by M5.
- `DockerRuntime`: per-runtime install/configure/switch argv; ddev-snapshot prompt path;
  selection precedence.
- `macos-defaults`: typed write argv; verify read-back; restart only on change.
- Dotfiles: `.chezmoiignore` rendered for darwin / linux / omarchy via
  `chezmoi execute-template` (skip if chezmoi absent); `zsh -n shell.zsh`; `bash -n shell.bash`.
- CI: checks on `ubuntu-22.04` and `macos-15`. End-to-end: the author's Mac.

## 8. Rollout (one PR each)

| # | Milestone | Outcome |
|---|---|---|
| M1 | Engine core (OsMap.macos, Brew, casks, BrewTap, headless fix, launchd, NeedsUser, root guard, contract test w/ xfail) | engine runs on Darwin |
| M2 | Shell + dotfiles (env/aliases split, shell.zsh, .zprofile/.zshrc, .chezmoiignore fix, zsh-config) | `devboost install terminal` from the clone |
| M3 | Catalog mapping (formulae/casks, provided_by/families sweep, xcode-clt, homebrew, `macos` profile) | most of the workstation |
| M4 | Docker runtimes + `devboost docker use` + launchd timers | ddev, Aspire, data-services |
| M5 | macos-defaults, stats, xcode, ios-tooling | iOS/RN + desktop |
| M6 | Delivery (darwin binary, get.sh, self-update, CI matrix) + `docs/macos.md` + README | fresh Mac via `curl … \| bash` |

## Out of scope

Intel Macs; Homebrew tap distribution; `brew bundle` batching; tiling WM / Karabiner /
launcher apps; Mac as a brain host or USB builder; notarization with an Apple Developer ID.
