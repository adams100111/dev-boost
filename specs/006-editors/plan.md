# Implementation Plan: editors

**Branch**: `006-editors` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-editors/spec.md`

## Summary

Deliver the `editors` profile as **three escape-hatch modules + one reusable helper lib +
one `profiles.toml` entry**, with zero engine/`bin/devboost` change. `vscode` adds the
Microsoft dnf repo, installs `code`, and installs a curated baseline extension list
(idempotent against `code --list-extensions`). `fresh` installs the Rust terminal editor
(`sinelaw/fresh`) from its Fedora `.rpm` (GitHub releases), with the official install
script and `cargo install --locked fresh-editor` as ordered fallbacks. `fresh-lsp`
provisions `fresh`'s language intelligence: it installs each language server/formatter as
a **mise-managed, version-pinned tool** (`mise use -g <backend>:<tool>@<pin>`) and
jq-merges the matching `lsp` entry into `~/.config/fresh/config.json` — applying the
**always-on base set** (markdown/toml/bash/json-yaml) that the `editors` profile carries.
Per-stack servers (intelephense↔laravel, basedpyright↔python, …) are **data added by the
later dev-stacks feature**, each reusing the new `lib/fresh.sh` helper, so profile-scoping
falls out of the engine's natural "select a profile → get its modules" behaviour (a
non-selected stack's server is simply never installed). All modules verify on the END
state (re-run is a no-op). With only `[install].fedora` keys, the engine already reports
them **unsupported** on non-Fedora — no module guard. Built test-first with bats, stubbing
`dnf`/`rpm`/`code`/`mise`/`cargo`/`curl` — no real installs, no network, no editor launch.

## Technical Context

**Language/Version**: Bash (engine + modules + `lib/fresh.sh`); python3/jq existing (`jq` does the `config.json` merge).
**Primary Dependencies**: `dnf` (+ Microsoft `vscode.repo`) for `code`; `rpm`/`curl` (fresh `.rpm` from GitHub releases) with `cargo install --locked fresh-editor` fallback; `mise` (existing base module) as the source of every LSP/formatter via its `npm:`/`cargo:`/`go:`/`github:`/`aqua:` backends; `code` CLI (`--list-extensions`/`--install-extension`) for headless extensions; `jq` for the idempotent `lsp`-block merge. No new engine runtime dependency.
**Storage**: system packages, the per-user `~/.vscode` extension dir, `~/.config/fresh/config.json`, and mise's pinned tool installs. No database.
**Testing**: `bats`; extend `tests/fixtures/base/stubs.bash` (backward-compatible) with `code` (extension-list knob + repo add), `mise` (`use -g`/`which` + installed-tool knob), and `fresh` install (`curl`/`rpm -U`/`cargo` + `command -v fresh`). Real `jq` exercises the merge. No real installs/network/editor (§V).
**Target Platform**: Fedora Workstation (reference). Non-Fedora → engine-reported unsupported (only `[install].fedora` keys).
**Project Type**: Single-project Bash bootstrap engine.
**Performance Goals**: Not latency-sensitive; correctness + idempotency.
**Constraints**: Unattended; idempotent (verify on end state); engine untouched; pins recorded (`config/mise.toml`); no secret in git.
**Scale/Scope**: 3 modules (`vscode`, `fresh`, `fresh-lsp`) + `lib/fresh.sh` + 1 `profiles.toml` entry (`editors`) + curated VS Code extension list (data) + `fresh` base-config template (data) + the stack→server map (documented data, base subset applied now) + ~3 bats files. Reuses Spec-1/2 escape-hatch + `lib/pkg.sh`. Per-stack server wiring is consumed by dev-stacks (Spec 7).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS. No engine touch (`run_install`/`depsort`/`module.sh`/`profile.sh`/`bin/devboost` unchanged). 3 modules + 1 profile entry are data/escape-hatch. `lib/fresh.sh` is a profile-helper library consumed by modules (same pattern as `lib/secrets.sh`/`lib/github.sh`/`lib/gnome.sh`), not control flow. Per-stack servers are added later as data (one module per stack), so "adding a language server = one module" holds.
- **II. Idempotent & Verify-Guarded** — PASS. `vscode` verify = `code` present AND every baseline extension already in `code --list-extensions` (installs only missing). `fresh` verify = `command -v fresh`. `fresh-lsp` verify = every base-set tool present in mise AND its `lsp` entry present in `config.json`; the jq-merge is idempotent (re-merge yields identical file) and never clobbers non-`lsp` keys. A failure names the module + exact command.
- **III. Reproducible — Repo is Source of Truth** — PASS. Every LSP/formatter is installed via `mise use -g <backend>:<tool>@<pin>` with pins recorded in `config/mise.toml`; curated extension list + base-config template + stack→server map all live in the repo. No secrets, no auto-commit.
- **IV. Unattended by Default** — PASS. `dnf -y`, `code --install-extension`, the fresh installers, and `mise use -g` are all non-interactive; extension install is a CLI op needing no graphical session.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. vscode repo+install+extensions+idempotent skip; fresh primary-install + fallback chain; `lib/fresh.sh` mise-install + jq-merge (base set wired, non-`lsp` keys preserved, re-run no-op); editor-missing→named-fail; unsupported-OS — all failing-bats-first, all tooling stubbed.
- **VI. Cross-OS via Data (Fedora reference)** — PASS. Only `[install].fedora` keys ⇒ engine reports unsupported on other OS (FR-013 by data, no guard). The stack→server map and extension list are in-repo data.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)
```text
specs/006-editors/
├── plan.md, research.md, data-model.md, quickstart.md
├── checklists/requirements.md
├── contracts/
│   ├── vscode.md          # MS repo + code + curated extensions (US1)
│   ├── fresh.md           # fresh install + fallback chain (US2)
│   ├── fresh-lsp.md       # lib/fresh.sh + base-set provisioning + jq-merge (US3)
│   └── profiles.md        # editors profile entry + depsort
└── tasks.md               # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)
```text
modules/                       # NEW editors modules (escape-hatch)
├── vscode/
│   ├── module.toml           # requires=[]; verify code + all baseline extensions
│   ├── install.sh            # add MS vscode.repo + dnf install code; install missing baseline extensions
│   └── extensions.txt        # DATA: curated baseline extension IDs (one per line)
├── fresh/
│   ├── module.toml           # requires=[]; verify command -v fresh
│   └── install.sh            # .rpm from GitHub releases (rpm -U) → install.sh → cargo --locked fallback
└── fresh-lsp/
    ├── module.toml           # requires=["fresh","mise"]; verify base-set tools + lsp entries present
    ├── install.sh            # seed base config.json if absent; provision the always-on base set via lib/fresh.sh
    ├── config.base.json      # DATA: base config (theme=catppuccin-mocha, editor defaults, formatter+format-on-save)
    └── servers.base.tsv      # DATA: always-on base set rows (lang, fresh-command, mise backend:tool@pin)
lib/
└── fresh.sh                  # NEW helper: fresh_lsp_provision <lang> <cmd> <backend:tool@pin>  (mise use -g + mise which + jq-merge lsp block)
config/mise.toml              # EDIT — record base-set tool pins
profiles.toml                 # EDIT — add `editors = ["vscode","fresh","fresh-lsp"]`
tests/
├── vscode.bats, fresh.bats, fresh-lsp.bats   # NEW
└── fixtures/base/stubs.bash  # EXTEND (backward-compatible): code (list/install-extension + repo), mise (use -g/which + tools), fresh install (curl/rpm -U/cargo)
```

**Structure Decision**: Single-project Bash engine; fully additive. No engine/`bin/devboost`
change. `lib/fresh.sh` is the one shared helper (mise-install + `mise which` resolve +
idempotent jq-merge of the `lsp` block) reused by `fresh-lsp` now and by each dev-stacks
per-stack module later. Profile-scoping is structural: the `editors` profile installs only
the always-on base set; selecting a stack profile (Spec 7) pulls in that stack's own
fresh-lsp module, so a non-selected stack's server is never installed — no conditional
logic in the engine or any module.

## Complexity Tracking

> No constitution violations. `lib/fresh.sh` follows the established profile-helper-lib
> pattern (`lib/secrets.sh`/`lib/github.sh`/`lib/gnome.sh`); no engine control-flow change.
> Table empty.
