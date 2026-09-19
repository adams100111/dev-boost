# dev-boost on macOS

Apple Silicon Macs are a first-class dev-boost target (constitution v3.1.0, Principle VI).
Design: `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This page grows with
each milestone. **Status: M3 — the workstation.** `devboost install` (the `macos` profile)
installs the whole catalog; Docker and the scheduled jobs arrive in M4, the desktop layer
in M5, `curl … | bash` in M6.

- Desktop layer, iOS and extras (M5): see [macos-primer.md](macos-primer.md).

## Requirements

- Apple Silicon (Intel is refused). macOS 27 Golden Gate or 26 Tahoe; 15 is best-effort.
- To run from a clone (until M6's installer): the Command Line Tools for git
  (`xcode-select --install`) and uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
  dev-boost itself installs and maintains the CLT, Homebrew (analytics off) and Rosetta 2.
- Run as your normal user, never with `sudo`: Homebrew refuses root. The password is
  requested lazily: a run prompts once, only when a planned, pending module actually needs
  sudo (`xcode-clt`, `homebrew`, `rosetta`, `tailscale`); a re-run where those are already
  done never asks for your password.

## Install from a clone

```sh
git clone https://github.com/adams100111/dev-boost ~/repos/dev-boost
cd ~/repos/dev-boost/engine
brew install uv && uv sync
uv run devboost install --dry-run   # see the plan (default profile on a Mac is `macos`)
uv run devboost install
```

Open a new Ghostty window afterwards. The next run skips everything that is already
installed.

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

Tools come from Homebrew, never `which`: macOS ships old copies of git, curl and bash that
would otherwise look installed.

More precisely: `--update` on macOS runs `brew upgrade` / `brew upgrade --cask` for every
module whose whole macOS install is exactly one Homebrew formula or cask — Zed included,
since its macOS install is the `zed` cask. A cask that updates itself (brew's
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

## One-time manual steps

A step only you can do is reported as **blocked** with the exact fix, and the rest of the
run carries on. Run `devboost install` again afterwards.

| When | What to do |
|---|---|
| `tailscale` blocked | Open Tailscale from the menu bar, allow its VPN configuration (System Settings → General → Login Items & Extensions → Network Extensions) and sign in — or add `TAILSCALE_AUTHKEY` to the secrets bundle. The Mac joins as a client (no Tailscale SSH server). A hand-installed `/Applications/Tailscale.app` is left alone — Homebrew's cask step skips it rather than trying to adopt it — and dev-boost never overwrites a `~/.local/bin/tailscale` it didn't write itself. dev-boost only opens the app to prompt for approval in an interactive run; an unattended run reports blocked with "open Tailscale and approve" instead. |
| `ddev` blocked | Run `mkcert -install` in a terminal once; macOS asks for your password to trust the local CA. |
| `zed` blocked | Run `devboost install zed` in a terminal and answer the "use Zed?" dialogs (one per file type). |
| `xcode-clt` blocked | Rare: run `xcode-select --install` and click Install. |
| a cask is `present-unmanaged` | You installed that app by hand and Homebrew cannot take it over; dev-boost leaves it alone. |

## Not on macOS yet (M4)

`docker`, `docker-build-gc`, `aspire-gc`, `restic-backup`, `restic-b2` and `obsidian-sync`
report **blocked: not automated on macOS yet (lands in M4)** with a manual workaround;
`data-services` and `ddev` `require` Docker directly, and `laravel-lsp` requires `ddev`, so
all three are blocked too until Docker lands. (`aspire`, the CLI tool, does not need Docker
to install — only `aspire-gc`, the orphaned-container GC timer, waits for M4.) Until then:
`brew install colima docker docker-compose && colima start`.

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

## Linux gate for this milestone

The shared shell files this milestone touches (`env.sh`, `aliases.sh`, `shell.bash`,
`.chezmoiignore`, the tmux/starship scripts) are Linux-facing too. Since a Fedora/Ubuntu VM
rehearsal (`scripts/vm-test.sh`) cannot run from this Mac (no libvirt), M2's Linux gate is
CI (`ubuntu-22.04`) plus hermetic `chezmoi apply` tests for `("linux", "fedora")` and
`("linux", "ubuntu")`. The real VM rehearsal moves to M6's CI matrix (`vm-smoke`).

## Coming next

M4 — Docker runtimes (Colima default) and launchd timers. M5 — desktop layer (defaults,
AeroSpace, Raycast, default-apps, …) and the opt-in iOS profile. M6 — `curl … | bash` on a
fresh Mac.
