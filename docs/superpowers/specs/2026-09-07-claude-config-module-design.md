# Claude Code config module — design

**Date:** 2026-09-07
**Status:** Design (brainstormed + grilled; pending final spec review)
**Mission fit:** Extends dev-boost's chezmoi-dotfiles + secrets + zero-config pattern to the
developer's *own Claude Code configuration*, so a fresh laptop reaches the same fully-configured
Claude Code (global instructions, rules, plugins, marketplaces, MCP servers, global skills) in
minutes, and a change made once propagates to every device via a normal git release.

> This revision incorporates the grilling pass (Q1–Q8) and the verified facts about Claude Code
> plugin/MCP/skill provisioning. Superseded assumptions from the first draft are called out in §10.

---

## 1. Goal & non-goals

**Goal.** A single, versioned, reusable-across-devices definition of the operator's global Claude
Code setup, applied by the dev-boost engine. Editing the repo and re-running the installer
(`chezmoi apply` + the engine) reproduces the setup on any device.

**In scope (the reusable surface):**
- Global instructions & rules — `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` (incl. a new
  `commit-conventions.md` capturing Conventional Commits + the anti-attribution rule).
- Plugins & marketplaces — `enabledPlugins` + `extraKnownMarketplaces`, **installed imperatively**.
- MCP servers — **`google-docs` and `fathom` only** (see §5 for why `context7` and `gdocs-batch`
  are dropped).
- Global skills — reproduced via the `skills` CLI from the lockfile, plus a small vendored set.
- (Already managed by existing modules: `statusline.sh`, `hooks/notify.sh`, and the
  `claude-statusline`/`claude-notify` settings merges.)

**Out of scope (deliberately device-/project-local):**
- Editor/UX settings (`theme`, `effortLevel`, `tui`, `voice`, `editorMode`, `skip*` flags).
- The auto-memory store (`~/.claude/projects/<path>/memory/*.md`, `MEMORY.md`) — per-project,
  path-keyed, agent-mutated working state.
- `gdocs-batch` MCP (device-local; a private node repo cloned where actually used).
- All runtime/machine state (`~/.claude.json` blob, `history.jsonl`, `sessions/`, plugin caches, …).

---

## 2. Key decisions (brainstorming + grilling)

1. **Repo = single source of truth, one-way apply.** Author in the repo; commit = release; devices
   apply via `curl … | bash` / `chezmoi apply`. A **one-time hybrid import** seeds the repo (§6).
2. **Decomposition = dotfiles + three small modules** (Approach B; §9).
3. **Skills = declarative (`npx skills`) + vendor-the-rest.** Loop `npx skills add <owner/repo@skill>
   -g -y` over each `~/.agents/.skill-lock.json` entry (~85 skills, recreates real dirs + the
   `~/.claude/skills` symlinks); the qa-e2e-pilot *plugin* delivers its 13; **vendor the ~14 non-lock
   dirs** (Cloudflare family, `context7-mcp`, `find-docs`, `sharpen`, `turnstile-spin`). [Q8]
4. **Secrets = `pass`-primary.** `google-docs`/`gdocs-batch` already resolve `$(pass …)` at runtime;
   move `CLICKUP_API_TOKEN` into `pass` too. The age bundle is left untouched (git/PAT only). The
   committed config holds no plaintext. `pass` is assumed pre-provisioned per device (GPG key +
   entries); modules `verify` it and fail loudly if absent. [Q2, Q3]
5. **Plugins install imperatively.** Shipping `enabledPlugins`/`extraKnownMarketplaces` is *not*
   sufficient (Claude Code ≥ v2.1.195); `claude-plugins` runs `claude plugin install
   <name>@<marketplace>` per plugin, **after `Secrets`**, with git-auth for the one private
   marketplace (`clickup-flow`). [fact]
6. **`context7` MCP dropped** (redundant with the enabled plugin; also removes a plaintext key). [Q1]
7. **`gdocs-batch` MCP excluded** as device-local (private node repo, not present even here). [Q7]
8. **Memories = preferences only.** Durable preferences → managed `CLAUDE.md`/`rules`; auto-memory
   store not synced.
9. **Degrade + report** when a secret/auth can't be resolved: apply all non-secret config, warn per
   item, return non-zero `verify`. [Q6]

---

## 3. Architecture

### 3.1 Delivered as chezmoi dotfiles (no new module)

The existing `Dotfiles` module runs `chezmoi apply --source <root>/dotfiles`. Static, secret-free:

- `dotfiles/private_dot_claude/CLAUDE.md` → `~/.claude/CLAUDE.md`
- `dotfiles/private_dot_claude/rules/*.md` → `~/.claude/rules/*.md` (existing four + new
  `commit-conventions.md`)
- `dotfiles/private_dot_claude/skills/<name>/…` → `~/.claude/skills/<name>` — the **~14 vendored**
  non-lock skills only
- `dotfiles/private_dot_agents/.skill-lock.json` → `~/.agents/.skill-lock.json` (the skills manifest)

### 3.2 Three new modules (imperative, idempotent)

| Module | Job | `requires` |
|---|---|---|
| `claude-plugins` | `gh auth setup-git`; add marketplaces (incl. `clickup-flow` `directory→github`, private); run `claude plugin install <name>@<marketplace>` per enabled plugin (idempotent); resolve `pass clickup/api-token` → git-ignored `settings.local.json` `env.CLICKUP_API_TOKEN` | `ClaudeCode`, `Dotfiles`, `Secrets` |
| `claude-skills` | Loop `npx skills add <owner/repo@skill> -g -y` over each lock entry (recreates real dirs + `~/.claude/skills` symlinks); vendored dirs arrive via `Dotfiles` | `ClaudeCode`, `Dotfiles` |
| `claude-mcp` | Register `google-docs` + `fathom` via `claude mcp add --scope user` (idempotent: `claude mcp list` → add-if-missing). No apply-time secret injection: `google-docs` self-resolves `pass` in its `bash -lc` wrapper; `fathom` does per-device interactive OAuth | `ClaudeCode`, `Dotfiles` |

Modules follow the existing `claude-statusline`/`claude-notify` shape (class-var metadata, `verify`,
`install`, read-merge-write for any `settings.json` touch). Typed manifests (plugin list, marketplace
map, MCP server defs) live as constants **inside the module files** (`mypy`-checked, diffable).

### 3.3 Profile

```toml
claude = ["claude-code","claude-plugins","claude-skills","claude-mcp"]
```

Name `claude` is disjoint from every module name (collision rule honored). Added to `full`;
`claude-code` already appears in `cli`, and transitive expansion de-duplicates. A fleet/shared box
drops `claude` from its profile set.

---

## 4. Data flow

```
chezmoi apply (Dotfiles) ─► ~/.claude/{CLAUDE.md, rules/, skills/<vendored>}, ~/.agents/.skill-lock.json
Secrets                  ─► ~/.git-credentials (PAT)          # prerequisite for private marketplace
claude-plugins           ─► gh auth setup-git
                            add marketplaces (clickup-flow → github, private)
                            claude plugin install <name>@<marketplace>   ×N   (idempotent)
                            pass clickup/api-token → settings.local.json env (0600, gitignored)
claude-skills            ─► for each lock entry: npx skills add <owner/repo@skill> -g -y
claude-mcp               ─► claude mcp list; add-if-missing google-docs, fathom  (--scope user)
```

### Safety invariants
1. **Merge, never clobber** any `settings.json`/`settings.local.json` write (pattern from
   `claude-statusline`).
2. **Corruption-tolerant**: absent settings → create; unparseable → leave untouched + report.
3. **Never hand-edit `~/.claude.json`**: MCP goes through `claude mcp`; plugins through
   `claude plugin install`.
4. **Zero plaintext in the repo**: secrets live only in `pass`; the sole on-disk decrypted value is
   `settings.local.json` (0600, git-ignored) for CLICKUP.
5. **Idempotent re-runs**: `verify` gates each module; `plugin install`/`mcp add` check-before-add.

---

## 5. Secrets & MCP inventory (post-grilling)

| Server / token | Decision | Secret mechanism | Portability note |
|---|---|---|---|
| `context7` MCP | **Drop** | — | Redundant with the enabled `context7` plugin; had a plaintext `ctx7sk-…` key |
| `google-docs` MCP | Keep | `$(pass google-docs/…)` in `bash -lc` (runtime) | Public npm pkg `@a-bonus/google-docs-mcp`; needs `pass` entries |
| `gdocs-batch` MCP | **Exclude (device-local)** | `$(pass …)` + private node repo | `adams100111/gdocs-batch-mcp` (private), not present here |
| `fathom` MCP | Keep | Interactive OAuth via `mcp-remote` | Public pkg; **one-time per-device browser auth** |
| `CLICKUP_API_TOKEN` (clickup-flow plugin) | Move to `pass` | `pass clickup/api-token` → `settings.local.json` env at apply time | Was plaintext in `settings.json`; scrubbed by import |

Verified constraints shaping the above:
- **Plugins do not auto-install** from settings alone → imperative `claude plugin install` (§2.5).
- **`${VAR}` does not expand from `settings.local.json`** (only in `.mcp.json`, from ambient env) →
  CLICKUP is written as a **concrete value** into git-ignored `settings.local.json` `env` (device-
  local, 0600), resolved from `pass` at apply time; no `${VAR}` indirection.
- **`pass` is a hard prerequisite** for `google-docs` (runtime) and CLICKUP (apply time). Modules
  `verify` `pass` + required entries and fail loudly with a clear message if missing (degrade+report).

---

## 6. One-time import (migration)

A hybrid `scripts/import-claude-config.sh` (run once, review diff, commit):

- **Mechanical (automated):** copy current `~/.claude/CLAUDE.md` + `rules/*.md` into the chezmoi
  source; copy `~/.agents/.skill-lock.json` (drop the `.bak-*` files); rewrite the `clickup-flow`
  marketplace `directory → github: adams100111/clickup-flow` (private); **scrub plaintext secrets** —
  remove `CLICKUP_API_TOKEN` from `settings.json` (record for `pass clickup/api-token`) and delete
  the standalone `context7` MCP (with its inline key).
- **Judgment (surfaced for review):** classify the 56 real `~/.claude/skills` dirs — lock-tracked
  (reproduced by `npx skills`, drop) vs non-lock (~14, vendor). Operator confirms the vendor set.
- Add `commit-conventions.md` (Conventional Commits `feat:`/`fix:`/… + anti-attribution).
- The 13 qa-e2e-pilot skill symlinks are ignored (plugin-delivered).

---

## 7. Prerequisites (per device)

- `pass` (passwordstore.org) initialized with the GPG key and entries:
  `google-docs/dits_client_id`, `google-docs/dits_client_secret`, `clickup/api-token`.
- Git credentials for the private `clickup-flow` marketplace (the existing `Secrets` module writes
  `~/.git-credentials` from the age PAT; `claude-plugins` runs `gh auth setup-git`).
- Node/`npx` (provided transitively by `claude-code` via mise) for `npx skills`.
- `fathom` requires a one-time interactive OAuth per device (documented, not automatable).

---

## 8. Testing

Per-module pytest under `engine/tests/modules/`, `FakeExecutor` + `HOME=tmp_path`, mirroring
`test_shell.py`'s Claude tests:

- `test_claude_plugins.py` — marketplace add incl. `directory→github`; `claude plugin install`
  invoked once per enabled plugin; skips-with-warning when `pass`/git-auth absent (degrade+report);
  CLICKUP written to `settings.local.json` (0600) with **no plaintext in any committed artifact**.
- `test_claude_skills.py` — `npx skills add` invoked per lock entry; idempotent on re-run; vendored
  dirs untouched.
- `test_claude_mcp.py` — `claude mcp list` consulted, `add` only for missing servers, `--scope user`;
  only `google-docs` + `fathom` registered (no `context7`/`gdocs-batch`).

Merge gates unchanged: `mypy --strict`, ruff, pytest from `engine/`.

---

## 9. Alternatives considered

- **A — one fat `claude-config` module.** Rejected: untestable blob; violates one-concern-per-file.
- **C — pure chezmoi.** Rejected: `settings.json` can't be static (runtime state + merges); plugins
  need imperative install, skills need `npx skills`, secrets need resolution.
- **Bidirectional live-capture update model.** Rejected for repo-as-source [Q: update model].
- **age-primary secrets.** Rejected: only CLICKUP would use it, forcing an age-bundle re-provision;
  `pass` is already the operational mechanism [Q2].
- **`npx skills update` for re-hydration.** Rejected in favor of explicit per-entry `add` (no
  documented lock→install reconcile; per-entry is deterministic) [Q8].

---

## 10. Superseded first-draft assumptions (corrected here)

- "Shipping `enabledPlugins`/`extraKnownMarketplaces` hydrates plugins" → **false**; imperative
  install required (§2.5, §5).
- "Inject 3 MCP env tokens via age" → **wrong inventory**; only CLICKUP is a token, via `pass`;
  Google uses `pass` at runtime, fathom uses OAuth, context7 dropped (§5).
- "age default + pass opt-in" → **pass-primary** (§2.4).
- "Vendor only ~1 local skill" → **~14 non-lock dirs vendored** (§2.3).
- "MCP `${VAR}` resolves from `settings.local.json`" → **false**; concrete value written instead (§5).

---

## 11. Open items / follow-ups (non-blocking)

- If `npx skills add <owner/repo@skill>` proves flaky for some pstack/mattpocock entries, fall back
  to vendoring those too (the mechanism is identical to the ~14 already vendored).
- `pass`-store provisioning is a documented prerequisite, not automated; a future `claude-passwords`
  step could bootstrap it from the age bundle (deferred, its own mini-project).
- Confirm `fathom`'s `mcp-remote` OAuth cache location so a re-auth isn't forced on every apply.
