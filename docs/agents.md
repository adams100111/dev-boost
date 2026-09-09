# AI agent tooling (modules)

dev-boost reproduces your AI coding-agent setup across devices. Install a profile with
`devboost install <profile>`. The **Claude**, **Codex**, and **Pi** bundles are part of `full`
(every workstation); **Orca** is opt-in.

## Profiles at a glance

| Profile | Installs | In `full`? |
|---|---|---|
| `claude` | Claude Code CLI + plugins + skills + MCP servers | yes |
| `codex` | OpenAI Codex CLI + config + plugins + MCP + skills | yes |
| `pi` | `pi-harness` — bootstraps your Pi harness (`harness-cli`) | yes |
| `orca` | `orca-ide` — Orca desktop app + `orca-ide` CLI | no (opt-in) |
| `orca-box` | `orca-ide` + `orca-serve` — headless Orca server | no (opt-in) |

## Claude / Codex

`devboost install claude` / `codex` (both already in `full`). Each reproduces your marketplaces,
enabled plugins, skills (the shared `~/.agents/skills`), and MCP servers. Integration secrets (e.g.
CLICKUP) come from your `pass` store — set `DEVBOOST_PASS_REPO` (see the security-cli profile). You
sign in to each CLI once per box.

## Pi

`devboost install pi` (in `full`). dev-boost bootstraps your own
[`agent-harness`](https://github.com/adams100111/agent-harness) (`harness-cli`) onto `PATH`; that
CLI — driven by its git-tracked manifest — then installs and configures everything under `~/.pi`.
dev-boost does **not** replicate `~/.pi` config (that would drift from your manifest). Requires the
secrets-bundle GitHub PAT to have read access to the private harness repo. First session: `pi /login`
(`devboost doctor` reminds you). Override the harness source with `DEVBOOST_HARNESS_REPO` /
`DEVBOOST_HARNESS_REF`.

## Orca

[Orca](https://github.com/stablyai/orca) is an Electron multi-agent development environment (it
orchestrates Claude/Codex/etc. in parallel git worktrees — bring your own agent CLIs/keys).

- **Laptop:** `devboost install orca` → the desktop app + CLI. Installed natively per-OS: Fedora
  `.rpm` (dnf), Ubuntu `.deb` (apt), Omarchy/Arch via the AUR `stably-orca-bin` package. The Linux
  command is `orca-ide` (or `stably-orca` on Arch). Pin a version with `DEVBOOST_ORCA_VERSION`.
- **Headless box:** `devboost install orca-box` → also installs a systemd `--user` service that runs
  `orca-ide serve` under your user with linger enabled (survives logout). It needs a **pairing
  address** clients dial: set `DEVBOOST_ORCA_PAIRING_ADDRESS`, or leave it and dev-boost derives your
  **Tailscale IP** (`tailscale ip -4`). Port defaults to `6768` (`DEVBOOST_ORCA_PORT`). The first run
  prints an `orca://pair?code=…` in the service journal — read it with
  `journalctl --user -u orca-serve` and pair a laptop/mobile client. Fedora/Ubuntu only. Headless
  Orca does not self-update; re-run `devboost install orca-box --force` (then
  `systemctl --user restart orca-serve`) to upgrade.

## Environment variables

| Variable | Module(s) | Default | Meaning |
|---|---|---|---|
| `DEVBOOST_PASS_REPO` | `pass-store` | — | git URL of your `pass` store to clone (claude/codex secrets) |
| `DEVBOOST_PASS_GPG_ID` | `pass-store` | — | GPG id to initialize a new store (when not cloning) |
| `DEVBOOST_HARNESS_REPO` | `pi-harness` | `adams100111/agent-harness` | the Pi harness repo to bootstrap |
| `DEVBOOST_HARNESS_REF` | `pi-harness` | `main` | branch / tag / SHA of the harness to install |
| `DEVBOOST_ORCA_VERSION` | `orca-ide` | latest | pin a specific Orca release (Fedora/Ubuntu) |
| `DEVBOOST_ORCA_PAIRING_ADDRESS` | `orca-serve` | Tailscale IP | host clients dial to pair |
| `DEVBOOST_ORCA_PORT` | `orca-serve` | `6768` | port `orca-ide serve` binds |
| `DEVBOOST_NTFY_URL` | `claude-notify` | — | ntfy topic for phone push on Claude task-done |

## First-run authentication (once per box — not automatable)

| Agent | Step |
|---|---|
| Claude | sign in to `claude` |
| Codex | sign in to `codex` |
| Pi | `pi /login` |
| Orca | pair with the `orca://pair?code=…` from the desktop app or the `orca-serve` journal |
