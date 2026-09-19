# dev-boost on macOS

Apple Silicon Macs are a first-class dev-boost target (constitution v3.1.0, Principle VI).
Design: `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This page grows with
each milestone. **Status: M2 — the terminal tier.** `devboost install terminal` (= the
`macos` profile for now) gives you the CLI toolset, zsh, Ghostty and the dotfiles.

## Requirements

- Apple Silicon (Intel is refused). macOS 27 Golden Gate or 26 Tahoe; 15 is best-effort.
- Until M3/M6 automate them: the Xcode Command Line Tools (`xcode-select --install`) and
  Homebrew (<https://brew.sh>) installed once by hand.
- Run as your normal user, never with `sudo`: Homebrew refuses root, and dev-boost asks for
  your password once when a step needs it.

## Install from a clone

```sh
git clone https://github.com/adams100111/dev-boost ~/repos/dev-boost
cd ~/repos/dev-boost/engine
brew install uv && uv sync
uv run devboost install terminal --dry-run   # see the plan
uv run devboost install terminal
```

Open a new Ghostty window afterwards. The next run skips everything that is already
installed.

## What you get

| Kind | Modules |
|---|---|
| Homebrew formulae | coreutils, git, wget, jq, mise, chezmoi, ripgrep, fd, fzf, bat, eza, btop, zoxide, atuin, direnv, delta (`git-delta`), lazygit, dust, duf, sd, yq, gh, tealdeer, fastfetch, tmux, fresh (`fresh-editor`), starship, bash (a tool — zsh stays your login shell), zsh-plugins (zsh-autosuggestions + zsh-syntax-highlighting) |
| Homebrew casks | ghostty, nerd-fonts (`font-jetbrains-mono-nerd-font`) |
| Provided by macOS (skipped) | curl, unzip, wl-clipboard (`pbcopy`/`pbpaste`) |
| Linux-only (not planned) | bash-config |
| Opt-in | `devboost install optional-terminals` → WezTerm nightly cask (deprecated) |

Tools come from Homebrew, never `which`: macOS ships old copies of git, curl and bash that
would otherwise look installed. `devboost install --update` upgrades the formulae; apps
such as Ghostty update themselves.

## Shell

zsh is the shell on macOS (bash on Linux). The files are shared where they can be:

| File | What it does |
|---|---|
| `~/.zprofile` | login shells, including the shells GUI apps start: `brew shellenv`, mise shims, then `~/.zprofile.local` |
| `~/.zshrc` | loads `~/.config/devboost/shell.zsh`, then `~/.zshrc.local` |
| `~/.config/devboost/env.sh` | POSIX env shared with bash: PATH, `LANG`, `XDG_CONFIG_HOME`, `ANDROID_HOME`, `RIPGREP_CONFIG_PATH`, `EDITOR`/`VISUAL`, then a machine-local override hook (see below) |
| `~/.config/devboost/aliases.sh` | `dev`, `expose`, `tsdev-sync`, `pw-*`, eza aliases — shared with bash |
| `~/.config/devboost/shell.zsh` | history, completion, fzf → mise → starship → atuin → zoxide → direnv, then the plugins |
| `~/.bash_profile` | for `bash -lc` launchers (MCP servers, scripts): `~/.profile` (if present), `env.sh`, `~/.bash_profile.local`, then `~/.bashrc` when interactive |

**Machine-local overrides.** `env.sh` ends by sourcing
`~/.config/devboost/local.sh` if it exists — dev-boost never ships or manages this file;
create it yourself for a one-off `PATH`/`EDITOR`/`VISUAL` tweak that shouldn't live in the
repo. It runs last, so it wins over everything else `env.sh` sets.

**Your old files are kept.** The first install **copies** (not moves — the original stays
in place) a `~/.zshrc`, `~/.zprofile` or `~/.bash_profile` that dev-boost did not write to
`<name>.pre-devboost`. It never overwrites an earlier backup; a later one becomes
`.pre-devboost.1`, and so on. Copy any lines you still need into `~/.zshrc.local` or
`~/.zprofile.local`, which dev-boost never touches.

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

## One-time manual steps

None for the terminal tier. If you installed Ghostty by hand earlier and Homebrew cannot
adopt it, the run reports `ghostty` as present-unmanaged and leaves your copy alone.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `zsh compinit: insecure directories` | not shown by design (`compinit -i`); to use brew's completions, run `chmod go-w "$(brew --prefix)/share"` |
| `ulimit: … invalid argument` at shell start | cannot happen: `shell.zsh` falls back to `kern.maxfilesperproc` until `macos-limits` (M5) raises the limit |
| `mosh`/ssh to Linux complains about `LC_CTYPE=UTF-8` | open a new shell. `env.sh` sets `LANG=en_US.UTF-8` and replaces a bare `LC_CTYPE=UTF-8` |
| lazygit / fresh ignore `~/.config` | the shell sets `XDG_CONFIG_HOME`. An app started from the Dock does not read your shell, so start it from a terminal |
| want your old shell back | `mv ~/.zshrc.pre-devboost ~/.zshrc` (then dev-boost will set it aside again on the next `dotfiles` run) |

## Linux gate for this milestone

The shared shell files this milestone touches (`env.sh`, `aliases.sh`, `shell.bash`,
`.chezmoiignore`, the tmux/starship scripts) are Linux-facing too. Since a Fedora/Ubuntu VM
rehearsal (`scripts/vm-test.sh`) cannot run from this Mac (no libvirt), M2's Linux gate is
CI (`ubuntu-22.04`) plus hermetic `chezmoi apply` tests for `("linux", "fedora")` and
`("linux", "ubuntu")`. The real VM rehearsal moves to M6's CI matrix (`vm-smoke`).

## Coming next

M3 — the full catalog on macOS (Homebrew and the CLT as modules, herdr, casks, the `macos`
profile). M4 — Docker runtimes (Colima default) and launchd timers. M5 — desktop layer.
M6 — `curl … | bash` on a fresh Mac.
