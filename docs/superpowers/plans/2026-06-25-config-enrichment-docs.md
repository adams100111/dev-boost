# Config Enrichment & Docs Refresh — Implementation Plan (config plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five curated, chezmoi-managed tool configs (bat, ripgrep, lazygit, delta-via-git, atuin) themed Catppuccin Mocha, and refresh README/docs to reflect the typed-Python engine + terminal/devtools tiers now on `main`.

**Architecture:** Pure dotfiles additions applied by the existing `dotfiles` module (`chezmoi apply --source $DEVBOOST_ROOT/dotfiles`). Each config is a new chezmoi source file under `dotfiles/dot_config/...`; ripgrep also needs a `RIPGREP_CONFIG_PATH` export in `dot_bashrc`. No engine or module-system changes. Docs are prose edits.

**Tech Stack:** chezmoi-managed dotfiles (TOML/YAML/gitconfig/rc files); BATS (`tests/dotfiles.bats`) for verification.

## Global Constraints

- **Single-copy / idempotent:** configs are chezmoi-managed source files; `chezmoi apply` replaces (never appends). No secrets in any managed file (FR-014).
- **Sentinel convention:** every managed config carries a `# devboost` marker comment (the bats suite asserts a `devboost` sentinel per file); match it.
- **Theme:** Catppuccin Mocha, consistent with `dotfiles/dot_config/starship.toml` + `dot_config/ghostty/config`. An unknown bat/delta theme is non-fatal (bat warns + falls back), but confirm availability via `bat --list-themes` and note it.
- **delta config goes in XDG `~/.config/git/config`** (chezmoi `dot_config/git/config`), NOT `~/.gitconfig` — the `secrets` module owns `~/.gitconfig` (identity/credentials via `git config --global`). Git merges both; only add pager/delta keys, never identity/credential keys.
- **Both suites green is the gate:** `bats tests/` (≥1138) stays green; the Python engine is unaffected.
- **Commits:** Conventional Commits, NO Claude/Anthropic attribution.
- **Test harness (tests/dotfiles.bats):** source-exists test form is `[ -f "${DEVBOOST_ROOT}/dotfiles/<path>" ]`; apply-writes uses the existing helper `_run_dotfiles_install` then `[ -f "${HOME}/.config/<path>" ]`.

**Out of scope:** aesthetic-only items (starship git_metrics/time/status, tmux Catppuccin status, nested-tmux F12); get.sh (next plan); no new tools.

---

## File Structure

```
dotfiles/dot_config/bat/config              # CREATE — bat config (Catppuccin, style=full)
dotfiles/dot_config/ripgrep/ripgreprc       # CREATE — rg config (glob-ignores, colors)
dotfiles/dot_bashrc                         # MODIFY — export RIPGREP_CONFIG_PATH
dotfiles/dot_config/lazygit/config.yml      # CREATE — lazygit (delta paging, nerdfonts 3)
dotfiles/dot_config/git/config              # CREATE — XDG git: delta pager + theme
dotfiles/dot_config/atuin/config.toml       # MODIFY — enrich (directory up-key, enter_accept, history_filter)
tests/dotfiles.bats                         # MODIFY — source/content/apply tests for each
README.md                                   # MODIFY — Bundled tool configs + typed engine/tiers
docs/architecture.md                        # MODIFY — dual-engine note
docs/adding-a-module.md                     # MODIFY — [fallback]/gui fields note
```

---

## Task 1: bat config

**Files:** Create `dotfiles/dot_config/bat/config`; Test `tests/dotfiles.bats`

**Interfaces:** Produces a chezmoi source applied to `~/.config/bat/config`.

- [ ] **Step 1: Write failing tests** — append to `tests/dotfiles.bats`:

```bash
@test "dotfiles: chezmoi source dot_config/bat/config exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config" ]
}

@test "dotfiles: bat config has devboost sentinel + style=full" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config"
  grep -q -- '--style="full"' "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config"
}

@test "dotfiles: apply writes ~/.config/bat/config into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/bat/config" ]
}
```

- [ ] **Step 2: Run — verify fail**

Run: `bats tests/dotfiles.bats -f 'bat config'`
Expected: FAIL — source file missing.

- [ ] **Step 3: Create `dotfiles/dot_config/bat/config`**

```
# ~/.config/bat/config — dev-boost managed bat configuration.
# devboost — managed by chezmoi; edit dotfiles/dot_config/bat/config in the dev-boost repo.
--theme="Catppuccin Mocha"
--style="full"
--italic-text=always
--pager="less -RFX"
--tabs=2
```

- [ ] **Step 4: Confirm the theme is available (non-fatal note)**

Run: `bat --list-themes 2>/dev/null | grep -qi 'Catppuccin Mocha' && echo OK || echo "fallback (bat will warn + use default; acceptable)"`
Expected: `OK` on bat ≥0.25; otherwise the unknown-theme warning is non-fatal — leave the config as-is and note it in the report.

- [ ] **Step 5: Run — verify pass**

Run: `bats tests/dotfiles.bats -f 'bat config'`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add dotfiles/dot_config/bat/config tests/dotfiles.bats
git commit -m "feat(dotfiles): add bat config (Catppuccin Mocha, style=full)"
```

---

## Task 2: ripgrep config + RIPGREP_CONFIG_PATH wiring

**Files:** Create `dotfiles/dot_config/ripgrep/ripgreprc`; Modify `dotfiles/dot_bashrc`; Test `tests/dotfiles.bats`

**Interfaces:** Produces `~/.config/ripgrep/ripgreprc`; `dot_bashrc` exports `RIPGREP_CONFIG_PATH` (rg reads its config ONLY from that env var).

- [ ] **Step 1: Write failing tests** — append to `tests/dotfiles.bats`:

```bash
@test "dotfiles: chezmoi source dot_config/ripgrep/ripgreprc exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc" ]
}

@test "dotfiles: ripgreprc ignores node_modules and lockfiles" {
  grep -q -- '--glob=!node_modules/' "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc"
  grep -q -- '--glob=!*.lock' "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc"
}

@test "dotfiles: dot_bashrc exports RIPGREP_CONFIG_PATH" {
  grep -q 'export RIPGREP_CONFIG_PATH=' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: apply writes ~/.config/ripgrep/ripgreprc into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/ripgrep/ripgreprc" ]
}
```

- [ ] **Step 2: Run — verify fail**

Run: `bats tests/dotfiles.bats -f 'ripgre'`
Expected: FAIL — missing file / missing export.

- [ ] **Step 3: Create `dotfiles/dot_config/ripgrep/ripgreprc`**

```
# ~/.config/ripgrep/ripgreprc — dev-boost managed ripgrep configuration.
# devboost — managed by chezmoi; edit dotfiles/dot_config/ripgrep/ripgreprc in the dev-boost repo.
--smart-case
--hidden
--glob=!.git/
--glob=!node_modules/
--glob=!dist/
--glob=!build/
--glob=!target/
--glob=!*.lock
--glob=!*.min.js
--glob=!*.map
--max-columns=300
--max-columns-preview
--colors=line:fg:yellow
--colors=path:fg:green
--colors=match:fg:red
```

- [ ] **Step 4: Wire the env var in `dotfiles/dot_bashrc`** — add, right after the `Path additions (user local bin)` block (before the tool initialisers):

```bash
# ripgrep — load the managed config (rg reads config only from this env var)
export RIPGREP_CONFIG_PATH="${HOME}/.config/ripgrep/ripgreprc"
```

- [ ] **Step 5: Run — verify pass**

Run: `bats tests/dotfiles.bats -f 'ripgre'`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add dotfiles/dot_config/ripgrep/ripgreprc dotfiles/dot_bashrc tests/dotfiles.bats
git commit -m "feat(dotfiles): add ripgreprc (glob-ignores) + RIPGREP_CONFIG_PATH wiring"
```

---

## Task 3: lazygit config

**Files:** Create `dotfiles/dot_config/lazygit/config.yml`; Test `tests/dotfiles.bats`

**Interfaces:** Produces `~/.config/lazygit/config.yml`.

- [ ] **Step 1: Write failing tests** — append to `tests/dotfiles.bats`:

```bash
@test "dotfiles: chezmoi source dot_config/lazygit/config.yml exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml" ]
}

@test "dotfiles: lazygit config wires delta paging + nerdfonts 3" {
  grep -q 'pager: delta' "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml"
  grep -q 'nerdFontsVersion: "3"' "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml"
}

@test "dotfiles: apply writes ~/.config/lazygit/config.yml into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/lazygit/config.yml" ]
}
```

- [ ] **Step 2: Run — verify fail**

Run: `bats tests/dotfiles.bats -f 'lazygit'`
Expected: FAIL — missing file.

- [ ] **Step 3: Create `dotfiles/dot_config/lazygit/config.yml`**

```yaml
# ~/.config/lazygit/config.yml — dev-boost managed lazygit configuration.
# devboost — managed by chezmoi; edit dotfiles/dot_config/lazygit/config.yml in the dev-boost repo.
gui:
  nerdFontsVersion: "3"
  border: "rounded"
git:
  paging:
    colorArg: always
    pager: delta --dark --paging=never
  autoFetch: true
update:
  method: never
```

- [ ] **Step 4: Run — verify pass**

Run: `bats tests/dotfiles.bats -f 'lazygit'`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add dotfiles/dot_config/lazygit/config.yml tests/dotfiles.bats
git commit -m "feat(dotfiles): add lazygit config (delta paging, nerdfonts 3)"
```

---

## Task 4: git/delta config (XDG, separate from secrets' ~/.gitconfig)

**Files:** Create `dotfiles/dot_config/git/config`; Test `tests/dotfiles.bats`

**Interfaces:** Produces `~/.config/git/config` — git merges this with `~/.gitconfig`; adds ONLY delta/pager keys (no identity/credentials).

- [ ] **Step 1: Write failing tests** — append to `tests/dotfiles.bats`:

```bash
@test "dotfiles: chezmoi source dot_config/git/config exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config" ]
}

@test "dotfiles: git config sets delta as pager and NO identity/credentials" {
  grep -q 'pager = delta' "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config"
  # must NOT manage identity/credentials (those belong to the secrets module / ~/.gitconfig)
  ! grep -qiE '^\s*(email|name|helper)\s*=' "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config"
}

@test "dotfiles: apply writes ~/.config/git/config into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/git/config" ]
}
```

- [ ] **Step 2: Run — verify fail**

Run: `bats tests/dotfiles.bats -f 'git config'`
Expected: FAIL — missing file.

- [ ] **Step 3: Create `dotfiles/dot_config/git/config`**

```gitconfig
# ~/.config/git/config — dev-boost managed git config (XDG; merged with ~/.gitconfig).
# devboost — managed by chezmoi; edit dotfiles/dot_config/git/config in the dev-boost repo.
# Identity + credentials are owned by the secrets module in ~/.gitconfig — never set them here.
[core]
	pager = delta
[interactive]
	diffFilter = delta --color-only
[delta]
	navigate = true
	line-numbers = true
	side-by-side = false
	syntax-theme = Catppuccin Mocha
[merge]
	conflictstyle = zdiff3
[diff]
	colorMoved = default
```

- [ ] **Step 4: Confirm delta + theme present (non-fatal note)**

Run: `command -v delta >/dev/null && bat --list-themes 2>/dev/null | grep -qi 'Catppuccin Mocha' && echo OK || echo "delta/theme absent here — config is inert until delta installed; theme warning non-fatal"`
Expected: `OK` where delta+bat≥0.25 present; otherwise note it (delta is in the terminal tier, so it'll be present after install; an absent syntax-theme is non-fatal).

- [ ] **Step 5: Run — verify pass**

Run: `bats tests/dotfiles.bats -f 'git config'`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add dotfiles/dot_config/git/config tests/dotfiles.bats
git commit -m "feat(dotfiles): wire delta as git pager via XDG git config (Catppuccin)"
```

---

## Task 5: atuin enrichment

**Files:** Modify `dotfiles/dot_config/atuin/config.toml`; Test `tests/dotfiles.bats`

**Interfaces:** Adds three settings to the existing atuin config; keeps all existing keys + the no-secrets invariant.

- [ ] **Step 1: Confirm the current history_filter schema** (do not guess) — verify against current atuin docs:

Run: `npx ctx7@latest docs "/websites/atuin_sh" "config.toml history_filter and enter_accept and filter_mode_shell_up_key_binding"` (or the atuin docs). Confirm whether `history_filter` is a top-level array (`history_filter = [...]`) or a table, and that `enter_accept` + `filter_mode_shell_up_key_binding` live under `[settings]`. Record what you confirmed in the report.

- [ ] **Step 2: Write failing tests** — append to `tests/dotfiles.bats`:

```bash
@test "dotfiles: atuin config enriches up-key (directory) + enter_accept" {
  grep -q 'filter_mode_shell_up_key_binding = "directory"' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
  grep -q 'enter_accept = true' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}

@test "dotfiles: atuin config has a history_filter for secret scrubbing" {
  grep -q 'history_filter' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}
```

- [ ] **Step 3: Run — verify fail**

Run: `bats tests/dotfiles.bats -f 'atuin config enriches'`
Expected: FAIL — settings not present.

- [ ] **Step 4: Edit `dotfiles/dot_config/atuin/config.toml`** — under `[settings]`, after the existing `search_mode_shell_up_key_binding = "fuzzy"` line, add:

```toml
# Pressing Up in the shell filters to commands run in the current directory.
filter_mode_shell_up_key_binding = "directory"

# Enter executes the selected command immediately; Tab puts it in the prompt to edit.
enter_accept = true

# Scrub obvious secrets from recorded history (on top of atuin's default secrets_filter).
# NOTE: place per the schema confirmed in Step 1 (top-level array vs table).
history_filter = [
  "(?i)password",
  "(?i)secret",
  "(?i)token",
  "--key[= ]",
]
```

(If Step 1 showed `history_filter` must be top-level — not under `[settings]` — place that single key at the end of the file instead, outside the `[settings]` table.)

- [ ] **Step 5: Run — verify pass + no-secrets invariant still holds**

Run: `bats tests/dotfiles.bats -f 'atuin'`
Expected: all atuin tests PASS (including the pre-existing `contains NO secrets or tokens` test — the filter patterns are regex literals, not secrets).

- [ ] **Step 6: Commit**

```bash
git add dotfiles/dot_config/atuin/config.toml tests/dotfiles.bats
git commit -m "feat(dotfiles): enrich atuin (directory up-key, enter_accept, history_filter)"
```

---

## Task 6: Documentation refresh

**Files:** Modify `README.md`, `docs/architecture.md`, `docs/adding-a-module.md`

**Interfaces:** Prose only. No code; the bats drift-gate (profiles table) must stay green.

- [ ] **Step 1: README — add a "Bundled tool configs" subsection.** Under the `## Profiles` or `## Quick start` section, add:

```markdown
## Bundled tool configs

dev-boost ships curated, chezmoi-managed configs (Catppuccin Mocha) applied by the
`dotfiles` module — single-copy and idempotent (no secrets):

| Tool | Config |
|------|--------|
| starship | minimal prompt (`dot_config/starship.toml`) |
| ghostty | terminal theme + font (`dot_config/ghostty/config`) |
| tmux | mouse, true-color, vi copy (`dot_tmux.conf`) |
| atuin | fuzzy history, directory up-key, enter-accept, secret-scrub |
| bat | `--style=full`, Catppuccin theme |
| ripgrep | glob-ignores (node_modules/dist/build/lockfiles); via `RIPGREP_CONFIG_PATH` |
| lazygit | delta paging, Nerd Fonts v3 |
| git/delta | delta as pager (XDG `~/.config/git/config`; identity stays in `~/.gitconfig`) |
```

- [ ] **Step 2: README — refresh Quick start / Commands for the typed engine + tiers.** Add a short note that, alongside the bash `bin/devboost` path, there is a typed-Python `devboost` engine exposing portable tiers:

```markdown
### Portable tiers (typed engine)

- `devboost terminal` — CLI/shell tools + dotfiles. Runs on any OS incl. a headless
  Ubuntu/Fedora VPS (auto-skips GUI-only pieces). Verify-guarded: re-running installs
  only what's missing; `--dry-run` previews.
- `devboost devtools` — language runtimes + frameworks (ddev, Aspire/.NET, Node, uv).

Both resolve the same declarative TOML modules/profiles as the bash engine, with a
distro-package-first, pinned-upstream-fallback install ladder. (A `curl … | bash`
bootstrap is planned.)
```

- [ ] **Step 3: docs/architecture.md — dual-engine note.** Add a section:

```markdown
## Engines (dual)

Per the constitution (v2.0.0), the engine may be implemented as pure Bash OR as a
strictly-typed Python engine shipped as a frozen single-file binary (no Python runtime
on the target). Both consume the same declarative TOML modules + `profiles.toml`:

- **Bash engine** — `bin/devboost` + `lib/*.sh` (the original; Fedora-reference, zero-config USB path).
- **Typed-Python engine** — `engine/devboost/` (Typer CLI), with the portable
  `terminal`/`devtools` tiers, headless auto-skip, and a distro→mise→script fallback ladder.

Design specs: `docs/superpowers/specs/2026-06-19-devboost-platform-design.md`,
`2026-06-25-portable-two-tier-installer-design.md`, `2026-06-25-ubuntu-parity-portable-tiers-design.md`.
```

- [ ] **Step 4: docs/adding-a-module.md — note the new manifest fields.** Add:

```markdown
### Optional manifest fields

- `gui = true` — marks a GUI-only module (e.g. a terminal app, fonts). The typed engine
  auto-skips it on headless boxes (no `$DISPLAY`/`$WAYLAND_DISPLAY`).
- `[fallback]` — used when the distro package is absent/stale. The engine appends these
  after the `[install].<os>` step: `mise = "aqua:<owner/repo>"` (or `cargo:`/`github:`),
  or `script = "<url>"` (run as `curl -fsSL <url> | sh`). Example:

  ```toml
  [install]
  fedora = "sudo dnf install -y eza"
  debian = "sudo apt-get install -y eza"
  [fallback]
  mise = "aqua:eza-community/eza"
  ```
```

- [ ] **Step 5: Verify both suites + drift-gate still green**

Run: `bats tests/ 2>&1 | tail -2` then `cd engine && . .venv/bin/activate && pytest -q 2>&1 | tail -1`
Expected: bats all green (the profiles drift-gate is unaffected by these prose edits); engine unchanged.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/architecture.md docs/adding-a-module.md
git commit -m "docs: document bundled tool configs + typed engine/terminal-devtools tiers"
```

---

## Self-Review

**Spec coverage:**
- §3.1 bat → Task 1. §3.2 ripgrep + wiring → Task 2. §3.3 lazygit → Task 3. §3.4 git/delta XDG → Task 4. §3.5 atuin enrich → Task 5. ✅
- §4 tests → per-task dotfiles.bats source/content/apply tests. ✅
- §5 docs (README configs + engine/tiers; architecture dual-engine; adding-a-module fields) → Task 6. ✅
- §2 decisions: delta in XDG git config (Task 4 + a test asserting NO identity keys); Catppuccin theme (Tasks 1/3/4); RIPGREP_CONFIG_PATH (Task 2). ✅

**Placeholder scan:** The two "confirm via context7 / bat --list-themes" steps (atuin schema, bat/delta theme) are explicit verification commands with stated fallbacks (non-fatal theme warning; schema-placement branch) — not deferred work.

**Consistency:** All tests use the real harness forms (`[ -f "${DEVBOOST_ROOT}/dotfiles/<path>" ]`, `_run_dotfiles_install` then `[ -f "${HOME}/.config/<path>" ]`) confirmed from tests/dotfiles.bats. chezmoi source→target mapping (`dot_config/X` → `~/.config/X`) holds for all five.

**Ordering:** Tasks 1–5 are independent config slices (any order); Task 6 (docs) last so it can describe the finished set. Each ends green on `bats tests/dotfiles.bats`.
