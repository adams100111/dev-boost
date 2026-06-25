# Config Enrichment & Docs Refresh — Design

**Status:** Draft spec (approved in brainstorming; lands on the impl branch)
**Date:** 2026-06-25
**Builds on:** Plans 1 (typed engine, merged `3df13f1`) + 2 (Ubuntu parity, merged `e7dd18f`)
**Source of ideas:** the user's `dotfiles-check/` reference repo (mined read-only, context7-verified; reference/inspiration only)

---

## 1. Summary

Two threads in one plan:
1. **Config enrichment** — dev-boost already *installs* bat/ripgrep/lazygit/delta/atuin but ships little or no *configuration* for them. Add five curated, chezmoi-managed configs (Catppuccin Mocha, matching the existing ghostty/starship theming) so these tools are useful out of the box.
2. **Docs refresh** — README/docs still describe only the old bash flow. Update them to reflect what is now on `main`: the typed-Python engine (`engine/`), the `terminal`/`devtools` tiers, verify-guarded installs, and the dual-engine constitution (v2.0.0). Plus document the new tool configs.

All config goes through the existing `dotfiles` module (`chezmoi apply --source`); no engine changes.

---

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|----------|
| 1 | Add 5 configs: bat, ripgrep, lazygit, git/delta, atuin-enrich. |
| 2 | **delta config lives in XDG `~/.config/git/config`** (chezmoi-managed) — NOT `~/.gitconfig`, which the `secrets` module owns (`git config --global` writes identity/credentials there). Git reads both; no collision. |
| 3 | **Catppuccin Mocha** theme for delta + lazygit (match existing ghostty/starship). |
| 4 | ripgrep needs `RIPGREP_CONFIG_PATH` exported in `dot_bashrc` to find its config. |
| 5 | **Docs: configs + full Plans 1–2 refresh** (README + docs/architecture for the typed engine + tiers). |

---

## 3. Component design — configs (chezmoi-managed under `dotfiles/`)

All files are chezmoi source files applied by the existing `dotfiles` module. Themes use the Catppuccin Mocha palette already used by `dotfiles/dot_config/starship.toml` + `dotfiles/dot_config/ghostty/config`.

### 3.1 `dotfiles/dot_config/bat/config`  *(verified: /sharkdp/bat)*
```
--theme="Catppuccin Mocha"
--style="full"
--italic-text=always
--pager="less -RFX"
--tabs=2
```
Note: bat finds `~/.config/bat/config` automatically (no env var). The `Catppuccin Mocha` theme requires the theme file be present in bat's themes dir; if bat lacks it built-in, fall back to a bundled theme (`--theme="base16"`/`TwoDark`) — confirm bat's available themes via `bat --list-themes` at implement time and pick the closest Catppuccin or a sane dark default.

### 3.2 `dotfiles/dot_config/ripgrep/ripgreprc`  *(verified: /burntsushi/ripgrep)*
```
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
Wiring: `dot_bashrc` exports `RIPGREP_CONFIG_PATH="$HOME/.config/ripgrep/ripgreprc"` (rg reads config ONLY from that env var).

### 3.3 `dotfiles/dot_config/lazygit/config.yml`  *(verified: /jesseduffield/lazygit)*
```yaml
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
(`nerdFontsVersion: "3"` matches the JetBrainsMono Nerd Font dev-boost installs; delta paging gives syntax-highlighted diffs in lazygit.)

### 3.4 `dotfiles/dot_config/git/config`  *(verified: /dandavison/delta)* — XDG, separate from `~/.gitconfig`
```gitconfig
[core]
    pager = delta
[interactive]
    diffFilter = delta --color-only
[delta]
    navigate = true
    line-numbers = true
    side-by-side = false
    syntax-theme = base16
[merge]
    conflictstyle = zdiff3
```
Rationale: `secrets` writes identity/credentials to `~/.gitconfig` via `git config --global`; git merges `~/.config/git/config` too, so delta settings here never collide. (Catppuccin delta theme can be added as a `[include] path` to a bundled theme file if desired; `syntax-theme = base16` is a safe always-present default — pick the closest Catppuccin syntax theme available in the delta/bat theme set at implement time.)

### 3.5 Enrich `dotfiles/dot_config/atuin/config.toml`  *(verified: /websites/atuin_sh)*
Add (keep existing keys):
```toml
filter_mode_shell_up_key_binding = "directory"
enter_accept = true
[history_filter]   # or `history_filter = [...]` per atuin's current schema — confirm at implement
# scrub secrets from history
```
Confirm the exact `history_filter` schema (top-level array vs table) against current atuin docs at implement time; use regexes for `password`, `token`, `secret`, `--key=` style flags on top of atuin's default `secrets_filter`.

---

## 4. Tests

`tests/dotfiles.bats` (extend): after the stubbed `chezmoi apply`, assert each new source file is present in the dev-boost dotfiles tree AND that `dot_bashrc` exports `RIPGREP_CONFIG_PATH`. The `dotfiles` module verify-gate may add a check that `~/.config/ripgrep/ripgreprc` (or the bat config) lands. Keep the existing single-copy/idempotency assertions. Both suites stay green (bats ≥1138; engine unaffected).

---

## 5. Documentation refresh

### 5.1 README.md
- **New subsection "Bundled tool configs"** under Profiles/Quick start: list the curated configs (starship, ghostty, tmux, atuin, **bat, ripgrep, lazygit, delta/git**) and that they're chezmoi-managed + Catppuccin-themed.
- **Quick start / Commands refresh:** document the typed-Python `devboost` engine and the portable tiers — `devboost terminal` (any OS incl. VPS, headless-aware), `devboost devtools` (runtimes/frameworks), alongside the existing `bin/devboost` bash path. Note verify-guarded idempotency (checks-before-install) and `--dry-run`.
- Note the eventual `curl … | bash` install is coming (Plan 3) without committing a URL yet.

### 5.2 docs/architecture.md
- Add a short section: **dual engine** — the bash engine + the typed-Python engine (`engine/`, Typer CLI) shipped as a frozen single-file binary, per constitution v2.0.0; both consume the same declarative TOML modules/profiles. Cross-link the two design specs.

### 5.3 docs/adding-a-module.md
- One note: the `[fallback]` table (mise/cargo/script) and `gui = true` fields the engine now understands, with a one-line example.

---

## 6. Out of scope (explicit)
- Aesthetic-only items the mining flagged to skip: starship `git_metrics`/`time`/`status`, tmux Catppuccin status bar, nested-tmux F12 toggle.
- get.sh public bootstrap (Plan 3, next).
- No new tools (dev-boost already installs every tool dotfiles-check had).

## 7. Risks
- **Theme availability:** "Catppuccin Mocha" may not be a built-in bat/delta theme; the spec falls back to a guaranteed-present dark theme and says to confirm available themes at implement time (don't hardcode a theme that errors).
- **atuin/`history_filter` schema** drift — confirm against current atuin docs (context7) before writing.
- **git config precedence:** `~/.config/git/config` must not duplicate keys `secrets` sets in `~/.gitconfig` (identity/credentials) — it only adds delta/pager keys, so no conflict.

## 8. Decomposition
One cohesive plan, ordered: configs (bat → ripgrep+wiring → lazygit → git/delta → atuin) → dotfiles.bats → docs. Each config is an independently testable slice.
