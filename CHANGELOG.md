# Changelog

Notable changes to dev-boost. Binaries ship as GitHub Releases (`v*` tags) —
see [releases](https://github.com/adams100111/dev-boost/releases). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Releases **≤ v0.1.77** predate this file; see
git history and the GitHub release notes.

## [Unreleased]

### Added
- **Docker runtimes on macOS (M4)** — Colima (default), OrbStack and Docker Desktop behind
  a common `DockerRuntime` protocol, plus `devboost docker use <runtime>` to switch between
  them (snapshots ddev first, stops the others, re-verifies what depends on Docker). ddev,
  Aspire and data-services now install on the Mac too. `aspire-gc`, `restic-backup`,
  `restic-b2`, `obsidian-sync` and `browser-mcp` (new — a Playwright MCP server for remote
  Claude Code sessions, `remote` profile) run as launchd agents, the macOS twin of the
  Linux systemd `--user` timers. `devboost doctor` reports the selected Docker runtime's
  health, with Apple M4/M5 and Rosetta-specific hints. `KNOWN_GAPS` is empty — M4 closes
  the macOS catalog. See [docs/docker-runtimes.md](docs/docker-runtimes.md).
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
- **macOS shell, terminal & dotfiles (M2)** — `devboost install terminal` runs on an
  Apple Silicon Mac: every terminal-set module installs through Homebrew
  (`BrewFormula`/`BrewCask` strategies, `per_os.macos`), zsh config (`shell.zsh`,
  `~/.zshrc`/`~/.zprofile` with `.local` hooks, `zsh-config`, `zsh-plugins`), brew `bash`,
  foreign rc files kept as `*.pre-devboost`, `docs/macos.md`.
- **`pass` multi-device (P1, Linux)** — per-device GPG keys (fingerprint-only access and
  trust; email ids in `.gpg-id` never grant access), enroll → approve → sync onto a shared
  private GitHub `pass` store, scoped enrollment for servers, revoke + a rotation checklist
  `devboost doctor` tracks until it's clear, a post-commit push hook plus a 15-min systemd
  user timer that also pushes a store whose first push never landed. New `devboost pass`
  CLI (`status`/`devices`/`enroll`/`approve`/`revoke`/`sync`). `pass` / `pass-store` move
  to `base` (the `security-cli` profile is now an alias for both). See
  [docs/pass.md](docs/pass.md).
- **`pass` multi-device on macOS (P2)** — pinentry-mac + the same gpg-agent cache TTLs as
  Linux, a launchd sync agent (`dev.devboost.pass-sync`, every 15 min), Notification
  Center notices (`osascript`), `devboost pass` now works on macOS too, and `pass` /
  `pass-store` join the `macos` profile. **Recipient audit** — `devboost pass audit`,
  `devboost doctor`'s `pass-recipients` check, and a sync notice flag any entry not
  encrypted to exactly its `.gpg-id` keys (reads packets only, never decrypts). See
  [docs/pass.md](docs/pass.md).
- **macOS engine core (M1)** — macOS family + arm64 normalization, Homebrew manager
  (formulae/casks/taps), launchd primitive, NeedsUser/PresentUnmanaged, macOS
  privacy-permission tracking (`devboost permissions`), macOS invocation rules (no root,
  one sudo prompt, keep-awake), gh-first/keychain credentials (`devboost secrets
  import-key`), macOS doctor, catalog contract test. Constitution v3.1.0.
- **Zed is the default editor on Linux** — `zed` module (official installer; Fedora, Ubuntu,
  Arch/Omarchy), seeded VS Code-style settings with Claude/Codex/Pi agents and dev-boost-pinned
  language servers, `config.jsonc_merge_deep` (comment-tolerant deep merge), and
  `VISUAL="zed --wait"` in local GUI sessions. See [docs/zed.md](docs/zed.md).

### Changed
- PyYAML is a new runtime dependency (Colima's `colima.yaml`).
- herdr 0.7.5 → 0.9.1 on every OS; catalog pins are keyed `<os>-<arch>`.
- `devboost install --update` on macOS upgrades Homebrew casks too, except apps that
  update themselves.
- `chezmoi-repo` runs `chezmoi init --apply --force`; a missing repo URL is `blocked`,
  not a failure.
- The Claude notify hook also shows a native macOS notification.
- **Ghostty is the default terminal on every OS**; WezTerm moved to the opt-in
  `optional-terminals` profile (deprecated) and its Ctrl+V smart paste was retired (herdr
  owns image paste).
- Shell config split into POSIX `env.sh` + shared `aliases.sh`; `shell.bash` uses
  `fzf --bash` when available (fallback for fzf < 0.48).
- One RAM/disk probe (`~/.local/bin/devboost-resources`, Linux + macOS) feeds tmux,
  starship, WezTerm and the Claude status line.
- Linux `PATH` order changed: `~/.local/bin` now comes first.
- `vscode` moved from `editors` to the opt-in `optional-editors` profile.

### Fixed
- The executor finds mise's shims where mise puts them (`MISE_DATA_DIR`, `XDG_DATA_HOME`).
- `.chezmoiignore` no longer fails on macOS (`.chezmoi.osRelease` is Linux-only).
- Ghostty config: `theme = Catppuccin Mocha` (Title Case) and `toggle_split_zoom` — the old
  values were rejected by Ghostty 1.3.
- `git credential fill` also neutralises `core.askPass`.
- Ubuntu/Debian: Ghostty installs as a classic snap (`snap install ghostty --classic`);
  Flathub has no Ghostty. A failed `flatpak install` now fails its module instead of
  passing silently.
- macOS: a dev-boost `~/.zshrc`/`~/.zprofile`/`~/.bash_profile` that another tool appended
  to is copied to `*.pre-devboost` before `chezmoi apply --force` (it used to lose those
  lines silently); a retried run makes no duplicate copy. `zsh-config` verify no longer
  crashes on a non-UTF-8 `~/.zshrc`.
- `zsh -i -c` without a terminal (an editor capturing the env) no longer prints
  `can't change option: zle`: the fzf and atuin key bindings load only on a tty.

### Removed
- `DEVBOOST_PASS_GPG_ID` — an empty store is now initialised by its first device
  ("genesis": generate the key, `pass init <fp>`, register, push) instead of a hand-made
  GPG id.

### Fixed
- systemd user units are daemon-reloaded after any rewrite (every devboost timer, not
  just `pass`'s), so a changed schedule takes effect without a re-login.
- `pass-store`'s verify now checks that the sync scheduler is actually loaded/enabled
  (systemd timer active, launchd agent loaded), not just that its unit/plist file exists.
- Unattended `pass` reads (`--pinentry-mode error`) never open a pinentry dialog nobody
  can answer; without a cached passphrase the secret is skipped, with a hint to run
  `pass show <entry> >/dev/null` once in a terminal to warm the cache.

### Docs
- Added [docs/pass.md](docs/pass.md) (the multi-device model, enroll/approve/sync, revoke
  + rotation, servers, disaster recovery); updated
  [docs/credentials.md](docs/credentials.md), [docs/recovery-runbook.md](docs/recovery-runbook.md),
  [docs/AGENTS.md](docs/AGENTS.md), [docs/architecture.md](docs/architecture.md) and
  [docs/adding-a-module.md](docs/adding-a-module.md) for the pass multi-device model and the
  `Module.after` ordering-only dependency.
- [docs/pass.md](docs/pass.md): macOS specifics (pinentry-mac, launchd sync agent,
  Notification Center), the recipient audit, and unattended-run behavior.

## [0.1.80] — 2026-09-09

### Added
- **Omarchy / Arch support** (#27) — a `pacman` package backend (official repos + AUR via
  `install_aur`), `ID_LIKE`-based Omarchy detection (`omarchy`/`cachyos`/`garuda` → `arch`), an
  `omarchy` profile, and the `omarchy-update-hook` module. Lands the previously-stranded
  `worktree-omarchy-support` work.
- **Orca module** (#28) — `orca-ide` installs [Orca](https://github.com/stablyai/orca) per-OS
  (Fedora `.rpm`, Ubuntu `.deb`, Omarchy/Arch AUR `stably-orca-bin`); `orca-serve` runs it headless
  via a systemd `--user` service (Xvfb, Tailscale-paired, linger). Opt-in `orca` / `orca-box`
  profiles. See [docs/agents.md](docs/agents.md).

### Fixed
- `test_omarchy` no longer depends on the host GPU marker (isolated `XDG_STATE_HOME`), so the suite
  is green on NVIDIA workstations as well as in CI.

### Docs
- Regenerated the README profiles/module tables for the claude/codex/pi + omarchy/orca modules (#26).
- Added this changelog and [docs/agents.md](docs/agents.md) (AI-agent module usage + env vars).

## [0.1.79] — 2026-09-08

### Added
- **`pi-harness` module** (#24) — bootstraps the operator's Pi coding-agent harness (`harness-cli`)
  and delegates `~/.pi` configuration to it (no duplication of its manifest). Opt-in `pi` profile,
  also in `full`. Informational `pi-login` doctor check. See [docs/agents.md](docs/agents.md).

## [0.1.78] — 2026-09-07

### Added
- **Claude Code config module** (#19) — `claude-code` / `claude-plugins` / `claude-skills` /
  `claude-mcp`; reproduces marketplaces, enabled plugins, skills, and MCP servers across devices.
  `claude` profile.
- **Codex config module** (#22) — `codex-code` / `codex-config` / `codex-plugins` / `codex-mcp` /
  `codex-skills` for the OpenAI Codex CLI. `codex` profile. Both `claude` and `codex` added to `full`.
- **`pass`-config validation** (#21) — `PassStore` hard-fails on missing config (clear `ConfigError`);
  informational `pass-config` doctor check.

### Fixed
- Claude CLICKUP token now written to `~/.claude/settings.json` (the file Claude actually reads), not
  the never-read user-level `settings.local.json` (#20).

---

Releases **v0.1.77 and earlier** predate this changelog — see the
[GitHub releases](https://github.com/adams100111/dev-boost/releases) and git history.
