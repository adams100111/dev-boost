# Claude Code config module — design

**Date:** 2026-09-07
**Status:** Design (approved in brainstorming; pending spec review)
**Mission fit:** Extends dev-boost's chezmoi-dotfiles + age-secrets + zero-config pattern to the
developer's *own Claude Code configuration*, so a fresh laptop reaches the same fully-configured
Claude Code (global instructions, rules, plugins, marketplaces, MCP servers, global skills) in
minutes, and a change made once propagates to every device via a normal git release.

---

## 1. Goal & non-goals

**Goal.** A single, versioned, reusable-across-devices definition of the operator's global Claude
Code setup, applied by the dev-boost engine. Editing the repo and re-running the installer
(`chezmoi apply` + the engine) reproduces the setup identically on any device.

**In scope (the reusable surface):**
- Global instructions & rules — `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` (incl. a new
  `commit-conventions.md`).
- Plugins & marketplaces — `enabledPlugins` + `extraKnownMarketplaces` in `~/.claude/settings.json`.
- MCP servers — `context7`, `google-docs`, `gdocs-batch`, `fathom`.
- Global skills — the loose skills under `~/.claude/skills` / `~/.agents/skills`.
- (Already managed by existing modules: `statusline.sh`, `hooks/notify.sh`, and the
  `claude-statusline`/`claude-notify` settings merges.)

**Out of scope (deliberately device-/project-local):**
- Editor/UX settings (`theme`, `effortLevel`, `tui`, `voice`, `editorMode`, `skip*` flags) — kept
  per-device.
- The auto-memory store (`~/.claude/projects/<path>/memory/*.md`, `MEMORY.md`) — per-project,
  keyed by absolute repo path, agent-mutated working state; not portable.
- All runtime/machine state (`~/.claude.json` blob, `history.jsonl`, `sessions/`, `tasks/`,
  plugin caches, `session-env/`, credentials).

---

## 2. Key decisions (from brainstorming)

1. **Repo = single source of truth, one-way apply.** Author changes in the dev-boost repo; commit =
   release; each device applies via the existing `curl … | bash` / `chezmoi apply` re-run. No
   capture/snapshot command. A **one-time import** seeds the repo from the current `~/.claude`.
2. **Decomposition = dotfiles + three small modules.** Pure files ride the existing `Dotfiles`
   (chezmoi) module; only merge/install/secret logic becomes modules. (Approach B; the fat-module
   and pure-chezmoi alternatives were rejected — see §7.)
3. **Skills = declarative + vendor-the-rest.** Reproduce upstream skills from
   `~/.agents/.skill-lock.json` via the skills-manager CLI; let the qa-e2e-pilot *plugin* deliver
   its 13; vendor only truly-local skills that have no upstream source.
4. **Secrets = age default, `pass` opt-in.** Decrypt the existing age bundle at apply time into a
   git-ignored `~/.claude/settings.local.json` / MCP env; support `pass` as an opt-in runtime
   resolver. The committed manifest holds only `${VAR}`/helper references — zero plaintext.
5. **Memories = preferences only.** Durable preferences (Conventional Commits, anti-attribution)
   live in managed `CLAUDE.md`/`rules`; the auto-memory store is not synced.

---

## 3. Architecture

### 3.1 Delivered as chezmoi dotfiles (no new module)

The existing `Dotfiles` module runs `chezmoi apply --source <root>/dotfiles`. Everything below is a
static file added to that source and delivered for free:

- `dotfiles/private_dot_claude/CLAUDE.md` → `~/.claude/CLAUDE.md`
- `dotfiles/private_dot_claude/rules/*.md` → `~/.claude/rules/*.md`
  (existing four + new `commit-conventions.md`)
- `dotfiles/private_dot_claude/skills/<name>/…` → `~/.claude/skills/<name>` — **only** vendored
  truly-local skills
- `dotfiles/private_dot_agents/.skill-lock.json` → `~/.agents/.skill-lock.json`

`private_` = 0600 perms. These files contain **no secrets**.

### 3.2 Three new modules (imperative, idempotent)

| Module | Job | `requires` |
|---|---|---|
| `claude-plugins` | Deep-merge `enabledPlugins` (19) + `extraKnownMarketplaces` (7) into `~/.claude/settings.json`; apply the `directory→github` fix for `clickup-flow` | `ClaudeCode`, `Dotfiles` |
| `claude-skills` | Ensure the skills-manager CLI is present; run it against the shipped `.skill-lock.json` to hydrate `~/.agents/skills` (idempotent). Vendored-local skills arrive via `Dotfiles` | `Dotfiles` |
| `claude-mcp` | Register the 4 MCP servers **via the `claude mcp` CLI** (idempotent), with env wired to `${VAR}`; decrypt the age bundle → write git-ignored `~/.claude/settings.local.json` (0600) and resolve MCP env | `ClaudeCode`, `Dotfiles`, `Secrets` |

Each module follows the existing `claude-statusline`/`claude-notify` shape in `modules/shell.py`
(class-var metadata, `verify`, `install`, read-merge-write into `settings.json`). Typed manifests
(the plugin/marketplace lists, MCP server definitions) live as constants **inside the module files**
so they are `mypy`-checked and diffable.

### 3.3 Profile

Add to `profiles.toml`:

```toml
claude = ["claude-code","claude-plugins","claude-skills","claude-mcp"]
```

Profile name `claude` is disjoint from every module name (`claude-code`, `claude-plugins`,
`claude-skills`, `claude-mcp`, `claude-statusline`, `claude-notify`), honoring the
profile≠module collision rule. `claude` is added to the `full` aggregate; `claude-code` already
appears in `cli`, and transitive expansion de-duplicates.

---

## 4. Data flow

```
chezmoi apply (Dotfiles) ─► ~/.claude/{CLAUDE.md, rules/, skills/<local>}, ~/.agents/.skill-lock.json
claude-plugins           ─► read settings.json → deep-merge enabledPlugins + extraKnownMarketplaces
                            → write back (preserve Claude Code runtime keys)
claude-skills            ─► ensure skills CLI → `skills install` from lockfile → ~/.agents/skills
claude-mcp               ─► `claude mcp add-json <name> …` (idempotent), env: "${VAR}"
                            age -d secrets.age ─► ~/.claude/settings.local.json (0600) + ${VAR} values
```

### Safety invariants
1. **Merge, never clobber.** Every `settings.json` write is read → deep-merge managed keys → write.
   Claude Code's runtime keys are preserved. (Exact pattern from `claude-statusline`.)
2. **Corruption-tolerant.** Absent `settings.json` → create; unparseable `settings.json` → leave
   untouched and report (mirrors `test_claude_statusline_leaves_invalid_json_untouched`).
3. **Never hand-edit `~/.claude.json`.** MCP registration goes through the `claude mcp` CLI so the
   runtime blob is owned by Claude Code, not us.
4. **Zero plaintext in the repo.** Committed manifests use `${VAR}`/helper references only; secret
   values exist solely in the age bundle and, at apply time, in 0600 `settings.local.json`.

---

## 5. Secrets

- **Default (age).** Reuse `modules/secrets.py` (`bundle_path()`, `key_path()`) and
  `primitives/age.py::decrypt()`. Add the required tokens (e.g. `CLICKUP_API_TOKEN`,
  `GOOGLE_DOCS_*`, `FATHOM_*`) to the age bundle JSON — `decrypt()` returns the whole dict, so new
  keys flow through automatically (pattern: `ObsidianSync.install`). At apply time `claude-mcp`
  writes them into git-ignored `~/.claude/settings.local.json` (0600) and MCP env.
- **Opt-in (`pass`).** On devices with `passwordstore.org` initialized, a helper resolves
  `pass show …` at runtime. For HTTP MCP servers this is Claude Code's `headersHelper`; for stdio
  servers it's a `command` wrapper (`bash -c 'TOK=$(pass show …) exec <server>'`). Selected via a
  device-local flag; the committed config is identical either way (`${VAR}`/helper refs).
- **Note:** Claude Code does **not** support `$(…)` command substitution in `settings.json`/MCP
  `env` — only `${VAR}` / `${VAR:-default}`. `apiKeyHelper` resolves the Anthropic key only. These
  constraints are why the resolver writes concrete values (age) or uses `headersHelper`/wrapper
  (`pass`), never inline command substitution.

---

## 6. One-time import (migration)

A hybrid `scripts/import-claude-config.sh` (run once, review the diff, commit):

- **Mechanical (automated):** copy current `~/.claude/CLAUDE.md` + `rules/*.md` into the chezmoi
  source; copy `~/.agents/.skill-lock.json`; rewrite the `clickup-flow` marketplace source from
  `directory` → `github: adams100111/clickup-flow`; **scrub the plaintext `CLICKUP_API_TOKEN`** out
  of `settings.json` and record it for the age bundle.
- **Judgment (surfaced for human review):** emit a skills classification report for the 56 real
  `~/.claude/skills` dirs — *upstream* (already covered by lockfile/plugin → drop) vs *local-only*
  (no upstream source → vendor into `dotfiles/private_dot_claude/skills/`). The operator confirms
  the vendor set before committing.
- Add the new `commit-conventions.md` rule (Conventional Commits `feat:`/`fix:`/… + the existing
  anti-attribution rule).

The 13 qa-e2e-pilot skill symlinks are ignored (delivered by the plugin).

---

## 7. Alternatives considered

- **A — One fat `claude-config` module.** Rejected: one large untestable blob; violates
  one-concern-per-file.
- **C — Pure chezmoi, no modules.** Rejected: `settings.json` can't be a static chezmoi file
  (Claude Code writes runtime state; existing modules *merge*); plugins need hydration, skills need
  the installer, secrets need decryption — none expressible in static chezmoi.
- **Bidirectional live-capture (snapshot) update model.** Rejected in favor of repo-as-source; a
  capture command adds complexity the operator did not want.
- **`pass` as the sole secret backend.** Rejected as default: forces a GPG-key bootstrap onto every
  device that the age/USB flow already solves. Kept as opt-in.

---

## 8. Testing

Per-module pytest under `engine/tests/modules/`, using `FakeExecutor` + `HOME=tmp_path`, mirroring
`test_shell.py`'s Claude tests:

- `test_claude_plugins.py` — merges preserving existing keys; creates when absent; leaves invalid
  JSON untouched; applies `directory→github`.
- `test_claude_skills.py` — skills CLI invoked with the lockfile; idempotent on re-run
  (no duplicate work when already installed).
- `test_claude_mcp.py` — `claude mcp` called once per server; age-decrypt writes a 0600 local file;
  **assert no plaintext token appears in any committed artifact**.

Merge gates unchanged: `mypy --strict`, ruff, pytest from `engine/`.

---

## 9. Open items / follow-ups

- Confirm the exact name/invocation of the skills-manager CLI that produced `.skill-lock.json`
  (version 3; sources `mattpocock/skills`, `cursor/plugins`) so `claude-skills` shells the right
  binary; if it is not trivially installable, fall back to vendoring those skills too.
- Confirm which MCP servers should be HTTP (eligible for `headersHelper`) vs stdio; the current four
  are stdio.
- Decide whether `gdocs-batch` (a custom local bash MCP server) ships its server script via dotfiles
  or is treated as device-local.
