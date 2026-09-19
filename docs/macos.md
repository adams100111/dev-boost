# dev-boost on macOS

Apple Silicon Macs are a first-class dev-boost target (constitution v3.1.0, Principle VI).
Design: `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This page grows with
each milestone. **Status: M1–M6 complete.** `curl … | bash` (`scripts/get.sh`, M6)
installs dev-boost itself with no clone and no Python; `devboost install` (the `macos`
profile) then installs the whole catalog, Docker (M4) and the desktop layer (M5) included.

- Desktop layer, iOS and extras (M5): see [macos-primer.md](macos-primer.md).

## Requirements

- Apple Silicon (Intel is refused), from a native (arm64) terminal: a Rosetta-translated
  shell (`sysctl -n sysctl.proc_translated` prints `1`) is refused up front with "open a
  native (arm64) terminal", because Homebrew's own installer aborts under Rosetta. macOS 27
  Golden Gate or 26 Tahoe; 15 is best-effort.
- Via `curl … | bash`: nothing to install first. `get.sh` bootstraps Homebrew itself when
  it's missing — which also installs the Xcode Command Line Tools — after a single
  `sudo -v` read from the tty (D4); a Homebrew that's already there is left alone. It does
  this only **after** the release binary has been downloaded and its checksum verified, so
  a missing asset or a bad checksum never leaves you with Homebrew and no dev-boost.
- To run from a clone instead: the Command Line Tools for git (`xcode-select --install`)
  and uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`). Either way, dev-boost itself
  installs and maintains the CLT, Homebrew (analytics off) and Rosetta 2.
- Run as your normal user, never with `sudo` — `get.sh` refuses to run as root before any
  download, and Homebrew itself refuses root too. The password is requested lazily: a run
  prompts once, only when a planned, pending module actually needs sudo (`xcode-clt`,
  `homebrew`, `rosetta`, `tailscale`); a re-run where those are already done never asks for
  your password.

## Install

**`curl | bash`** (recommended — no clone, no Python):

```sh
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- macos
```

In order: refuses root, the `usb` profile, Intel, a Rosetta shell and an unsupported
macOS; downloads the matching `devboost-darwin-arm64` binary from the latest GitHub Release
and verifies it against the release's `checksums.txt`; only then bootstraps Homebrew + the
CLT (when missing); installs the binary onto PATH (`~/.local/bin/devboost`); and runs
`devboost install macos`. If the latest release carries no Mac binary — every release before
v0.2.0 — it stops with `no devboost-darwin-arm64 in release <tag> yet — macOS support ships
in v0.2.0` and nothing on the machine has changed. See
[docs/credentials.md](credentials.md) for how the first run gets a GitHub token, and
"Self-update" and "Troubleshooting" below.

`DEVBOOST_RELEASE_BASE` overrides where `get.sh` fetches the binary and `checksums.txt`
from (default: the latest GitHub Release) — it exists for rehearsing an unpublished build
(see [docs/vm-testing.md](vm-testing.md), "macOS (tart)"; [docs/maintenance.md](maintenance.md)),
not for everyday installs. A non-default base warns loudly, naming the host, because both
the binary and the checksums that are supposed to vouch for it then come from the same,
un-official place.

**From a clone:**

```sh
git clone https://github.com/adams100111/dev-boost ~/repos/dev-boost
cd ~/repos/dev-boost/engine
brew install uv && uv sync
uv run devboost install --dry-run   # see the plan (default profile on a Mac is `macos`)
uv run devboost install
```

Open a new Ghostty window afterwards. The next run skips everything that is already
installed.

## Self-update

`devboost self-update` resolves the same `(os, arch)` release asset `get.sh` does: on
Apple Silicon that is `devboost-darwin-arm64` alone — no Ventoy archive is fetched or
replaced, since the injection tarball is a Linux-only artifact `build-bundle.sh` never
produces on Darwin. It downloads `checksums.txt` and the binary, verifies the SHA256
before touching anything on disk, and **refuses to install a version older than the one
currently running** (`refusing to downgrade <current> to <new> (latest release)`) — there
is no flag to override that; reinstall an older release explicitly via `get.sh` if you
ever need to go back. The swap itself is atomic (a temp file in the same directory, then
an `os.replace`), and since the download comes from `urllib` — not a browser — the new
binary carries no `com.apple.quarantine` attribute, so it keeps running with no Gatekeeper
prompt; it keeps the same ad-hoc PyInstaller signature the original binary shipped with,
since nothing here re-signs it.

A minor, currently-harmless asymmetry: `devboost.core.selfupdate.release_asset()` maps
*either* `arm64` or `aarch64` (case-insensitive) to `darwin-arm64`, while
`build-bundle.sh`'s `bb_arch` and `release.sh`'s `rl_arch` only match a literal `Darwin/arm64`
from `uname -m` — real Apple Silicon always reports `arm64` there, so this never actually
triggers, but it's worth knowing if either script is ever run under something that reports
`aarch64` instead (`get.sh`'s `gs_arch`, by contrast, already accepts both).

## What you get

| Kind | Modules |
|---|---|
| Foundation | `xcode-clt` (silent CLT install), `homebrew` (analytics off), `rosetta` (macOS ≤ 27) |
| Homebrew formulae | the terminal set (M2), plus glow, mosh, neovim (opt-in), uv, cmake (`build-tools`), smartmontools, ffmpeg (`multimedia`), utiluti, mkcert, ddev (`ddev/ddev` tap), colima, docker, docker-compose, docker-buildx |
| Homebrew casks | ghostty, nerd-fonts, zed, obsidian, bruno, bitwarden, localsend, vlc, tailscale-app, android-commandlinetools; opt-in: visual-studio-code, jetbrains-toolbox, wezterm@nightly, orbstack, docker-desktop |
| Own installers | .NET 10 SDK in `~/.dotnet` (`dotnet-install.sh`), herdr 0.9.1 (pinned, SHA-256-checked), Claude Code, Codex, the Pi harness |
| Scheduled jobs (M4) | `aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync` as launchd agents (systemd `--user` timers on Linux); `browser-mcp` — opt-in (`devboost install browser-mcp`): a LaunchAgent on macOS, the dotfiles' systemd unit on Linux, enabled only by the module |
| Same as Linux | mise runtimes (node/pnpm/bun, java, devops tools), LSP servers, Playwright, Aspire, csharp-ls, the Claude/Codex plugins, skills and MCP servers |
| Provided by macOS (skipped) | curl, unzip, wl-clipboard, flameshot (⌘⇧5), fwupd, thermald, power-profiles-daemon, va-hwaccel, bash-config (zsh is the login shell here; `zsh-config` covers it — reports `provided-by-macos`, not silently dropped) |
| Linux-only (not planned) | gearlever, earlyoom, gpu-detect, zram, the brain-host services, the Fedora system layer |

`devboost install --update` upgrades every Homebrew formula and cask in the plan, except
apps that update themselves (Zed, Ghostty, Obsidian, VS Code, Tailscale, …).

Tools come from Homebrew, never `which`: macOS ships old copies of git, curl and bash that
would otherwise look installed.

More precisely: `--update` on macOS runs `brew upgrade` / `brew upgrade --cask` for every
module whose whole macOS install is exactly one Homebrew formula or cask — Zed included,
since its macOS install is the `zed` cask, and so is every single-cask desktop app
(AeroSpace, Raycast, Stats, …). An app it already installed is never re-opened. A cask that updates itself (brew's
`auto_updates`: Zed, Ghostty, Obsidian, VS Code, Tailscale, …) is skipped by that upgrade
step, but the rest of the module's own logic still runs on an `--update` pass: for Zed, the
config merge always runs, and the default-apps step can still report `blocked` if the run
is unattended. Modules with their own macOS provisioning (a custom `per_os.macos` strategy,
not a bare formula/cask) are not part of `--update`, as on Linux.

## Shell

zsh is the shell on macOS (bash on Linux). The files are shared where they can be:

| File | What it does |
|---|---|
| `~/.zprofile` | login shells, including the shells GUI apps start and `zsh -lc` launchers: `brew shellenv`, mise shims, `env.sh`, then `~/.zprofile.local` |
| `~/.zshrc` | loads `~/.config/devboost/shell.zsh`, then `~/.zshrc.local` |
| `~/.config/devboost/env.sh` | POSIX env shared with bash: PATH, `LANG`, `XDG_CONFIG_HOME`, `ANDROID_HOME`, `RIPGREP_CONFIG_PATH`, `EDITOR`/`VISUAL`, then a machine-local override hook (see below) |
| `~/.config/devboost/aliases.sh` | `dev`, `expose`, `tsdev-sync`, `pw-*`, eza aliases — shared with bash |
| `~/.config/devboost/shell.zsh` | history, completion, fzf → mise → starship → atuin → zoxide → direnv, then the plugins |
| `~/.bash_profile` | for `bash -lc` launchers (MCP servers, scripts): `~/.profile` (if present), `env.sh`, `~/.bash_profile.local`, then `~/.bashrc` when interactive |

**bash on macOS.** dev-boost does not manage `~/.bashrc` on macOS (it is Linux-only in
`.chezmoiignore`), so an interactive bash reads **your own** `~/.bashrc`, if you have one —
dev-boost's prompt, aliases and tool inits are zsh-only there. `bash -lc` launchers still
get the shared `env.sh` through `~/.bash_profile`.

**`ZDOTDIR`.** dev-boost writes `~/.zshrc` and `~/.zprofile` in your home directory. If you
set `ZDOTDIR` (for example in `/etc/zshenv` or `~/.zshenv`), zsh reads the rc files from
that directory instead and never loads dev-boost's (`devboost verify` checks `~/.zshrc`,
so it does not notice). Unset
`ZDOTDIR`, or have `$ZDOTDIR/.zshrc` and `$ZDOTDIR/.zprofile` source `~/.zshrc` and
`~/.zprofile`.

**Machine-local overrides.** `env.sh` ends by sourcing
`~/.config/devboost/local.sh` if it exists — dev-boost never ships or manages this file;
create it yourself for a one-off `PATH`/`EDITOR`/`VISUAL` tweak that shouldn't live in the
repo. It runs last, so it wins over everything else `env.sh` sets.

**Your old files are kept.** Before it writes `~/.zshrc`, `~/.zprofile` or
`~/.bash_profile`, the `dotfiles` module **copies** (not moves — the original stays in
place) the current file to `<name>.pre-devboost` when dev-boost did not write it, or when
dev-boost wrote it but something has since changed it (an installer that appended a
`PATH` line, for example — the rewrite would otherwise drop that line). It never
overwrites an earlier backup; a later one becomes `.pre-devboost.1`, and so on, and a
re-run makes no second copy of an identical file. Move the lines you still need into the
matching `.local` file — `~/.zshrc.local`, `~/.zprofile.local` or `~/.bash_profile.local` —
which dev-boost never touches.

The Voxtype config (`~/.config/voxtype/config.toml`) and the AeroSpace config
(`~/.config/aerospace/aerospace.toml`) get the same one-time `.pre-devboost` copy. If you
keep your AeroSpace config at `~/.aerospace.toml` instead, dev-boost writes no
`~/.config/aerospace/aerospace.toml` at all (AeroSpace refuses to load when both exist)
and warns with both paths: merge its Ctrl+Alt bindings into your file yourself.

The same protection applies when `chezmoi-repo` points at your own external dotfiles repo
(`DEVBOOST_DOTFILES_REPO`, or `DOTFILES_REPO` in the secrets bundle): its `chezmoi init
--apply --force` backs up a drifted rc file first too, before handing the file over to
your repo. A missing repo URL is reported `blocked` (not a failure) with the variable to
set.

## Terminal — Ghostty

Ghostty is the default terminal on every OS. On macOS:

- **Left Option is Alt** (word jumps, fzf's Alt-C, herdr's Alt bindings). Right Option still
  types accents and special characters.
- **Cmd and Ctrl+Shift both work**: Cmd+C / Cmd+V copy and paste, Cmd+T new tab, Cmd+N new
  window, Cmd+Shift+→/← switch tabs, Cmd+Shift+Z zoom a split, Cmd+= / Cmd+- / Cmd+0 font
  size.
- **Ctrl+V is not bound.** Pasting an image into a remote agent is `herdr --remote`'s job.
- Over SSH, Ghostty installs its terminfo on the server (`ssh-terminfo`), so remote
  tools render correctly.
- A notification appears when a long command finishes while Ghostty is in the background.

RAM and disk gauges (tmux status line, starship prompt, Claude Code status line) read the
same probe, `~/.local/bin/devboost-resources`. On macOS it measures the data volume. The
probe self-caches its output for `DEVBOOST_RESOURCES_TTL` seconds (default 2; `0` disables
the cache) so a starship prompt with several resource-gated modules doesn't fork a probe
per module on every keystroke.

## Editor — Zed

Zed is the default editor on macOS too (see [zed.md](zed.md)): the `zed` cask, the same
`~/.config/zed/settings.json` seed and must-have keys as Linux, and Zed as the app that
opens code and text files (`data/macos/default-apps.tsv`). macOS 26.4+ asks you to confirm
each file type once; dev-boost remembers what it asked (`~/.local/state/devboost/default-apps.json`)
and never asks again, even if you said no.

`$EDITOR` / `$VISUAL`: put your own choice in `~/.config/devboost/local.sh` (for example
`export EDITOR=nvim VISUAL=nvim`). It is yours — dev-boost never writes it — and it is read
last, in every shell.

## Docker, ddev, Aspire and scheduled jobs (M4)

Colima is the default runtime; see [docker-runtimes.md](docker-runtimes.md) for the
licensing table and `devboost docker use`, which switches to OrbStack or Docker Desktop
later without losing anything.

`devboost install laravel dotnet data dev-hygiene` gives ddev (`brew install ddev/ddev/ddev`
+ `mkcert -install`), the Aspire CLI (a `dotnet tool` in `~/.dotnet`) and the data-services
compose template. The postgres, valkey and dbgate images it references are multi-arch.

The timers (`aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync`) are LaunchAgents
labelled `dev.devboost.<name>`. See
[docker-runtimes.md](docker-runtimes.md#scheduled-jobs-launchd) for the schedule and log
locations.

`browser-mcp` is **opt-in**: no profile installs it, not even `remote`. Turn it on with
`devboost install browser-mcp`, which loads an always-on agent. It runs
`@playwright/mcp@0.0.82`, pinned and never `@latest`, on the Mac's Tailscale IP at port 8931.
That server has `browser_run_code_unsafe`, which is RCE-equivalent, and no option turns it
off. Any tailnet peer that can reach tcp:8931 can run code as you, so restrict tcp:8931 with
a Tailscale ACL before you turn it on. See
[remote-dev.md](remote-dev.md#security-port-8931-runs-code-on-your-machine) for the policy.

## One-time manual steps

A step only you can do is reported as **blocked** with the exact fix, and the rest of the
run carries on. Run `devboost install` again afterwards.

| When | What to do |
|---|---|
| `tailscale` blocked | Open Tailscale from the menu bar, allow its VPN configuration (System Settings → General → Login Items & Extensions → Network Extensions) and sign in — or add `TAILSCALE_AUTHKEY` to the secrets bundle. The Mac joins as a client (no Tailscale SSH server). A hand-installed `/Applications/Tailscale.app` is left alone — Homebrew's cask step skips it rather than trying to adopt it — and dev-boost never overwrites a `~/.local/bin/tailscale` it didn't write itself. dev-boost only opens the app to prompt for approval in an interactive run; an unattended run reports blocked with "open Tailscale and approve" instead. |
| `ddev` blocked | Run `mkcert -install` in a terminal once; macOS asks for your password to trust the local CA. |
| `docker`/`docker-build-gc` blocked | A Colima home split, or a root-owned `~/.docker/config.json`/daemon config — the fix command is in the block's `NeedsUser` message; see [docker-runtimes.md](docker-runtimes.md#colima-details). |
| `obsidian-sync` blocked | Set `export DEVBOOST_VAULT_REPO=<repo>` (a GitHub repo name) and make GitHub credentials available (`gh auth login`, or `GIT_USER`/`GITHUB_PAT` in the secrets bundle). The block message names what is missing. |
| `restic-b2` blocked | Add `B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`, `RESTIC_REPOSITORY` and `RESTIC_PASSWORD` to the secrets bundle. restic itself is already installed. |
| `zed` blocked | Run `devboost install zed` in a terminal and answer the "use Zed?" dialogs (one per file type). |
| `xcode-clt` blocked | Rare: run `xcode-select --install` and click Install. |
| a cask is `present-unmanaged` | You installed that app by hand and Homebrew cannot take it over; dev-boost leaves it alone. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `zsh compinit: insecure directories` | not shown by design (`compinit -i`); to use brew's completions, run `chmod go-w "$(brew --prefix)/share"` |
| `ulimit: … invalid argument` at shell start | cannot happen: `shell.zsh` falls back to `kern.maxfilesperproc` until `macos-limits` (M5) raises the limit |
| `mosh`/ssh to Linux complains about `LC_CTYPE=UTF-8` | open a new shell. `env.sh` sets `LANG=en_US.UTF-8` and replaces a bare `LC_CTYPE=UTF-8` |
| lazygit / fresh ignore `~/.config` | the shell sets `XDG_CONFIG_HOME`. An app started from the Dock does not read your shell, so start it from a terminal |
| want your old shell back | `mv ~/.zshrc.pre-devboost ~/.zshrc`. `devboost verify` then reports `zsh-config` as failed (your `~/.zshrc` is no longer dev-boost's), and `devboost install dotfiles --force` copies it aside again and puts dev-boost's back |
| csharp-ls / aspire: "You must install .NET" | open a new shell: env.sh exports DOTNET_ROOT=~/.dotnet |
| herdr --remote from the Mac disconnects right away | herdr < 0.8 on either end — run devboost install on both machines (pin 0.9.1) |
| Gatekeeper blocks `devboost-darwin-arm64` ("cannot be opened because the developer cannot be verified") | Only a **browser**-downloaded binary is quarantined — `curl \| bash` never sets `com.apple.quarantine`, so `get.sh` and `self-update` are unaffected. Clear it: `xattr -d com.apple.quarantine ~/Downloads/devboost-darwin-arm64`, then `chmod +x` it. The binary carries PyInstaller's **ad-hoc** signature only — there is no Developer ID and no notarization — so if Gatekeeper still objects after the xattr is cleared, run it from a terminal, or allow it once under System Settings → Privacy & Security. |
| `get.sh`: `no devboost-darwin-arm64 in release <tag> yet — macOS support ships in v0.2.0` | The latest release predates macOS support (v0.2.0). Nothing was installed — not even Homebrew; re-run once v0.2.0 is out. |
| `get.sh`: `this shell runs under Rosetta (x86_64) — open a native (arm64) terminal` | Your terminal app is set to "Open using Rosetta" (Finder → Get Info) or you started an `arch -x86_64` shell. Open a native terminal and re-run; nothing was installed. |

## Linux gate

The shared shell files (`env.sh`, `aliases.sh`, `shell.bash`, `.chezmoiignore`, the
tmux/starship scripts) are Linux-facing too, but this doc is written and rehearsed from a
Mac, which cannot run the Fedora/Ubuntu libvirt VM (`scripts/vm-test.sh`). Two gates cover
it instead: CI (`ubuntu-24.04`) plus hermetic `chezmoi apply` tests for `("linux",
"fedora")` and `("linux", "ubuntu")`; and `.github/workflows/vm-smoke.yml`'s
`linux-smoke` job (M6) — Fedora and Arch containers plus the Ubuntu runner host itself,
each running `devboost install cli ghostty` for real and then `scripts/smoke-assert.sh`
against it, confirming Ghostty came from its real per-distro source (the `scottames/ghostty`
COPR, the snap, or pacman). `linux-smoke` is advisory (`continue-on-error: true`) until its
container-image dependencies (COPR, snap, pacman) prove stable across runs.
