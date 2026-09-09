# Changelog

Notable changes to dev-boost. Binaries ship as GitHub Releases (`v*` tags) —
see [releases](https://github.com/adams100111/dev-boost/releases). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Releases **≤ v0.1.77** predate this file; see
git history and the GitHub release notes.

## [Unreleased]

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
