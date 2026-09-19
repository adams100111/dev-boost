# Changelog

Notable changes to dev-boost. Binaries ship as GitHub Releases (`v*` tags) —
see [releases](https://github.com/adams100111/dev-boost/releases). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Releases **≤ v0.1.77** predate this file; see
git history and the GitHub release notes.

## [Unreleased]

### Added
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
  CLI (`status`/`devices`/`enroll`/`approve`/`revoke`/`sync`) — **Linux-only until P2**; on
  macOS it exits `` `devboost pass` is Linux-only ``. `pass` / `pass-store` move to `base`
  (the `security-cli` profile is now an alias for both). See [docs/pass.md](docs/pass.md).
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
- `.chezmoiignore` no longer fails on macOS (`.chezmoi.osRelease` is Linux-only).
- Ghostty config: `theme = Catppuccin Mocha` (Title Case) and `toggle_split_zoom` — the old
  values were rejected by Ghostty 1.3.
- `git credential fill` also neutralises `core.askPass`.

### Removed
- `DEVBOOST_PASS_GPG_ID` — an empty store is now initialised by its first device
  ("genesis": generate the key, `pass init <fp>`, register, push) instead of a hand-made
  GPG id.

### Docs
- Added [docs/pass.md](docs/pass.md) (the multi-device model, enroll/approve/sync, revoke
  + rotation, servers, disaster recovery); updated
  [docs/credentials.md](docs/credentials.md), [docs/recovery-runbook.md](docs/recovery-runbook.md),
  [docs/AGENTS.md](docs/AGENTS.md), [docs/architecture.md](docs/architecture.md) and
  [docs/adding-a-module.md](docs/adding-a-module.md) for the pass multi-device model and the
  `Module.after` ordering-only dependency.

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
