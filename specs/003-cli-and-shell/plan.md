# Implementation Plan: cli-and-shell

**Branch**: `003-cli-and-shell` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-cli-and-shell/spec.md`

## Summary

Deliver the `cli` and `shell` profiles as **data + escape-hatch modules over the existing
engine**, plus dev-boost's **chezmoi source tree** (`dotfiles/`) holding the shipped
configs, applied by a single `dotfiles` module. Most CLI tools are **pure-TOML modules**
(`verify = command -v X`, per-OS `[install]`); a few need escape hatches
(`claude-code` = npm global via mise-node → `requires=["mise"]`; `gh` repo; `ghostty`
COPR; `nerd-fonts` download). Starship is the default prompt (install + the
chezmoi-managed bash rc sources `starship init`, `atuin`, `zoxide`, `fzf`, `direnv`).
The `dotfiles` module runs `chezmoi apply` against dev-boost's source tree so the
opinionated starship.toml, bash rc, ghostty config, and tmux config land idempotently
(re-apply replaces managed files → no duplicate shell-init lines). Engine control flow is
untouched; **no `bin/devboost` change this time**. Built test-first with bats, extending
the Spec-2 `tests/fixtures/base` stub harness to fake `dnf`/`flatpak`/`cargo`/`npm`/
`mise`/`chezmoi`/`fc-list`/`curl`/COPR so no real installs or network occur.

## Technical Context

**Language/Version**: Bash (engine + modules); python3/jq (existing).
**Primary Dependencies**: leaf tools invoked by modules — `dnf`/`rpm` (+ COPR for ghostty), `mise`+`npm` (claude-code), `cargo`/binary installers where a tool isn't packaged, `chezmoi` (config apply), `fc-list`/font install, `curl`. No new engine runtime dependency.
**Storage**: user config only — chezmoi-applied dotfiles (`~/.bashrc`, `~/.config/starship.toml`, `~/.config/ghostty/config`, `~/.tmux.conf`, `~/.config/atuin`, `~/.claude/`), installed fonts under `~/.local/share/fonts` (or system), package state. No database.
**Testing**: `bats`; extend `tests/fixtures/base/stubs.bash` with cargo/npm/fc-list/copr stubs + a `chezmoi apply` stub; scratch `HOME`. No real installs/network (§V).
**Target Platform**: Fedora 44 reference (full); debian/macos thinner via per-OS keys (ghostty/some tools may be unsupported there → reported).
**Project Type**: Single-project Bash bootstrap engine.
**Performance Goals**: Not latency-sensitive; correctness + idempotency.
**Constraints**: Unattended; idempotent/verify-guarded; engine untouched; no secret in git; configs contain no secrets.
**Scale/Scope**: ~17 cli tool modules + 4 shell modules (starship, bash-config, ghostty, nerd-fonts) + 1 `dotfiles` apply module; add `cli`+`shell` to `profiles.toml`; organize `dotfiles/` into a chezmoi source; ~5 bats files. Reuses Spec-1/2 patterns; no new lib, no engine touch.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS (no engine touch at all). New capability is modules (data + escape-hatch) + the `dotfiles/` chezmoi source (data) + two `profiles.toml` entries. `run_install`/`depsort`/`module.sh`/`profile.sh`/`bin/devboost` unchanged. Cleaner than Spec 2 (no doctor addition needed).
- **II. Idempotent & Verify-Guarded** — PASS. Each tool module verifies by binary; `dotfiles` verify checks a sentinel of applied state; `chezmoi apply` is idempotent (managed files replaced, never appended → FR-007 no-duplicate).
- **III. Reproducible — Repo is Source of Truth** — PASS. Shipped configs live in the repo's `dotfiles/` chezmoi source; no secret committed; configs contain no secrets (FR-014).
- **IV. Unattended by Default** — PASS. All installs non-interactive; font/COPR installs scripted; chezmoi apply non-interactive.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. Each module + the apply idempotency + unsupported-OS + claude-code ordering are failing-bats-first; all externals stubbed.
- **VI. Cross-OS via Data** — PASS. Per-OS `[install]` keys; Fedora reference; ghostty/fonts unsupported elsewhere → engine reports it.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)
```text
specs/003-cli-and-shell/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── cli-tools.md          # the cli tool modules (+ claude-code escape hatch)
│   ├── shell-env.md          # starship, bash-config, ghostty, nerd-fonts
│   ├── dotfiles-apply.md     # the dotfiles module + chezmoi source layout
│   └── profiles.md           # cli + shell profile entries
└── tasks.md
```

### Source Code (repository root)
```text
profiles.toml                 # EDIT — add `cli` and `shell` profile entries
modules/                      # NEW cli + shell modules
├── eza.toml, bat.toml, btop.toml, zoxide.toml, atuin.toml, direnv.toml, delta.toml,
│   lazygit.toml, lazydocker.toml, dust.toml, duf.toml, sd.toml, yq.toml,
│   tealdeer.toml, tpm.toml, fastfetch.toml          # simple per-tool (pure TOML)
├── gh/{module.toml,install.sh}                       # GitHub CLI repo + install
├── claude-code/{module.toml,install.sh}              # requires=["mise"]; npm global
├── starship/{module.toml,install.sh}                 # install (curl/dnf)
├── ghostty/{module.toml,install.sh}                  # COPR scottames/ghostty + install
├── nerd-fonts/{module.toml,install.sh}               # download+install JetBrainsMono/Meslo; fc-cache
├── bash-config/module.toml                           # requires dotfiles; verify rc applied
└── dotfiles/{module.toml,install.sh}                 # chezmoi apply dev-boost source tree
dotfiles/                     # EDIT — organize into a chezmoi source (dot_* layout): bashrc,
                              #        config/starship.toml, config/ghostty/config, tmux.conf,
                              #        atuin/zoxide/fzf/direnv init, claude/ (import from ../setup-scripts §6.1)
tests/
├── cli-tools.bats, shell.bats, dotfiles.bats, fonts.bats   # NEW (cli.bats is the engine test — do NOT reuse)
└── fixtures/base/stubs.bash  # EXTEND (backward-compatible): cargo/npm/fc-list/copr/chezmoi-apply stubs
```

**Structure Decision**: Single-project Bash engine; fully additive + the `dotfiles/`
source-tree organization. No engine control-flow or `bin/devboost` change. Simple tools
are pure TOML; only repo/COPR/npm/font/apply logic uses escape hatches.

## Complexity Tracking

> No constitution violations — no engine touch. (The Spec-2 `doctor` drift addition is not
> repeated here.) Table intentionally empty.
