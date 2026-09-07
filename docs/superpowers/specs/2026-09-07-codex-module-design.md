# Codex config module — design

**Date:** 2026-09-07
**Status:** Design approved (brainstormed + fact-checked via context7 + web + local `~/.codex`).
**Mission fit:** Extends the reusable-across-devices agent-config pattern (see the `claude` module,
`2026-09-07-claude-config-module-design.md`) to **OpenAI Codex CLI**, so a fresh device reproduces
the operator's Codex setup (instructions, plugins, marketplaces, MCP servers, skills, prefs, hooks).

## Verified facts (not assumptions)

Confirmed via context7 (`/openai/codex`) + web + the live `~/.codex` (`codex-cli 0.149.0`):
- This is **real OpenAI Codex CLI** (`github.com/openai/codex`), a recent version. The `.system`
  skills (`imagegen`, `openai-docs`, `plugin-creator`, `skill-creator`, `skill-installer`) are
  Codex's **official bundled skills**. Plugins, marketplaces, skills, AGENTS.md, hooks are **genuine
  current Codex features** (not a fork).
- **Install:** standalone binary via `curl -fsSL https://chatgpt.com/codex/install.sh | sh`;
  self-updates via `codex update` (auto-detects install method). Binary lives at
  `~/.codex/packages/standalone/…`, symlinked to `~/.local/bin/codex`.
- **Codex's five core systems:** `config.toml` + sandbox/approval + `AGENTS.md` + MCP + skills.
- **CLI:** `codex plugin {add,list,marketplace,remove}`, `codex mcp {add,list,get,remove,login}`,
  `codex doctor`, `codex features`.
- Everything is consolidated into `~/.codex/config.toml` (TOML) + `~/.codex/AGENTS.md`.

## Concept mapping (Claude Code → Codex)

| Claude Code | Codex |
|---|---|
| `~/.claude/CLAUDE.md` + `rules/*.md` | `~/.codex/AGENTS.md` (one hierarchical file; no rules dir) |
| `settings.json` `enabledPlugins` | `config.toml` `[plugins."x@y"] enabled=true` |
| `extraKnownMarketplaces` | `config.toml` `[marketplaces.x]` (`source_type` git/local) |
| `mcpServers` | `config.toml` `[mcp_servers.x]` |
| `~/.claude/skills/` + `~/.agents` lock | `config.toml` `[[skills.config]]` (path→SKILL.md + enabled) + `~/.codex/skills/<name>/SKILL.md` |
| hooks in settings.json | `~/.codex/hooks.json` + `[hooks]` + `[features] hooks=true` |
| `effortLevel`/`theme` | `model`, `model_reasoning_effort`, `approval_policy`, `sandbox_mode` |
| CLICKUP env | `[shell_environment_policy.set] CLICKUP_API_TOKEN` |
| `claude plugin install` / `claude mcp add-json` | `codex plugin add` / `codex mcp add` |
| install npm `@anthropic-ai/claude-code` | `chatgpt.com/codex/install.sh` + `codex update` |
| auto-memory (md files) | `memories_1.sqlite` / `goals_1.sqlite` (SQLite machine-state, **not portable**) |

The live `~/.codex` already mirrors the Claude setup: same `claude-plugins-official` marketplace + the
same 18 plugins, same MCP servers (context7 with a plaintext `ctx7sk` key; google-docs/gdocs-batch via
`pass`), CLICKUP in `[shell_environment_policy.set]`, and the herdr/notify hooks. So this is a
**translation**, and the secrets already live in the operator's `pass` store.

## Decisions (from brainstorming)

1. **Instructions files: separate, global-only dotfiles.** Manage `~/.codex/AGENTS.md` (and the
   existing `~/.claude/CLAUDE.md`) as independent full-file dotfiles. The module NEVER touches
   **project-level** `CLAUDE.md`/`AGENTS.md` (which tools like laravel-boost write), only the global
   files — so per-harness/project files are safe. (Single-source rendering to both is a possible
   future enhancement, deliberately deferred.)
2. **Full skills parity:** port the vendored/local skills into Codex's `SKILL.md` + `[[skills.config]]`
   form (plugin-delivered skills come free via the enabled plugins).
3. **Version the whole reusable `config.toml` surface:** `[plugins]`/`[marketplaces]`/`[mcp_servers]`,
   `approval_policy`/`sandbox_mode`, `model`/`model_reasoning_effort`, `[shell_environment_policy]`,
   `[features]`, `[hooks]`. (For Codex the operator explicitly wants model/effort versioned too —
   unlike the claude module, where editor/UX prefs were device-local.)
4. **Secrets = reuse the existing `pass` store** (nothing new): CLICKUP → `[shell_environment_policy.set]`
   at apply time (device-local `config.toml`, never committed); drop the `context7` MCP (the plugin
   covers it, and it carried a plaintext key); google-docs/gdocs-batch resolve `pass` at runtime;
   `gdocs-batch` (private node repo) stays device-local/excluded.

## Architecture (mirrors the `claude` cluster)

**Dotfiles (chezmoi, global-only):** `dotfiles/private_dot_codex/AGENTS.md`,
`dotfiles/private_dot_codex/hooks.json`, `dotfiles/private_dot_codex/hooks/*`, and vendored
`dotfiles/private_dot_codex/skills/<name>/SKILL.md`.

**Modules (idempotent; TOML merge-not-clobber on `config.toml`):**

| Module | Job | `requires` |
|---|---|---|
| `codex-code` | Install standalone binary (`chatgpt.com/codex/install.sh`); `verify` = `which codex` | `Mise`(node for npx skills) |
| `codex-config` | Merge shareable `config.toml` prefs + `[features]` + `[shell_environment_policy]` (CLICKUP from `pass`) + `[hooks]`, preserving `[projects.*]` / `[hooks.state.*]` | `CodexCode`, `Dotfiles`, `PassStore` |
| `codex-plugins` | `codex plugin marketplace add` + `codex plugin add` per enabled plugin (clickup-flow `local`→github), idempotent | `CodexCode`, `Secrets` |
| `codex-mcp` | `codex mcp add` for `google-docs` (drop `context7`; `gdocs-batch` device-local) | `CodexCode` |
| `codex-skills` | Full parity — hydrate lockfile skills for Codex + vendored `SKILL.md` + `[[skills.config]]` | `CodexCode`, `Dotfiles` |

Plus a **`codex` profile** = `["codex-code","codex-config","codex-plugins","codex-mcp","codex-skills"]`,
added to `full`. Profile name `codex` is disjoint from every module name (collision rule).

## config.toml safety

`config.toml` is a **device-local home file, never committed** (like `~/.claude/settings.json`), so
the plaintext-free-repo invariant holds even though CLICKUP lands there. Managed sections are written
by **merge-not-clobber**: prefer the `codex` CLI where it owns the write (`codex plugin add`,
`codex mcp add` edit `config.toml` themselves and preserve the rest — Codex even exposes an atomic
`config/batchWrite`), and for pure-config sections a Python TOML merge that preserves `[projects.*]`
trust, `[hooks.state.*]` hashes, and any other device state.

## Verification spike (front of the plan — real facts before task code)

1. Exact `codex plugin marketplace add` / `codex plugin add` / `codex mcp add` syntax, scope, and
   idempotency (mirror the `claude plugin`/`claude mcp` verification).
2. How `npx skills` targets Codex — the lockfile carries `lastSelectedAgents`, implying the installer
   is multi-agent; determine the exact command to hydrate `~/.codex/skills` and whether it also writes
   `[[skills.config]]`.
3. Claude vs Codex `SKILL.md` format compatibility (for vendored-skill conversion), and a TOML
   **writer** for the engine — stdlib `tomllib` is read-only; confirm/add `tomli-w` (or equivalent)
   as an engine dependency for the `config.toml` merges.

## Not portable (machine-state, excluded)

`[projects.*]` trust, `[hooks.state.*]` hashes, all `*.sqlite` (memories/goals/logs/queue/state/
thread_history), `sessions/`, `cache/`, `auth.json`, `history.jsonl`, `models_cache.json`, and the
`.system` skills (reinstalled by the binary).

## Sources

- context7 `/openai/codex`; https://developers.openai.com/codex/skills ;
  https://developers.openai.com/plugins/build/plugins ;
  https://codex.danielvaughan.com/2026/05/08/codex-cli-codex-update-self-update-command/ ;
  https://blakecrosley.com/guides/codex
