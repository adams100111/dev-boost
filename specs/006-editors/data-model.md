# Phase 1 Data Model: editors

No database. "Data" = module manifests, the profile entry, the curated VS Code extension
list, the `fresh` base-config template, the stack→server map, and the resulting system /
per-user state (packages, `~/.vscode` extensions, `~/.config/fresh/config.json`, mise pins).

## Module entities
Escape-hatch modules (`modules/<name>/{module.toml,install.sh,…}`) sourcing `lib/log.sh`+`lib/pkg.sh`
(+ `lib/fresh.sh` for `fresh-lsp`). All `category="editors"`, only `[install].fedora` keys
(⇒ unsupported on non-Fedora by data).

| Module | requires | Extra data files |
|---|---|---|
| `vscode` | `[]` | `extensions.txt` (curated baseline IDs) |
| `fresh` | `[]` | — |
| `fresh-lsp` | `["fresh","mise"]` | `config.base.json` (base config), `servers.base.tsv` (always-on set) |

## profiles.toml (EDIT — add 1 entry)
```toml
editors = ["vscode","fresh","fresh-lsp"]
```
Part of the design's `full` set (Spec 12 assembles `full`). Profile-level "depends on base,
shell" is realized via `fresh-lsp requires ["fresh","mise"]` (mise ∈ base) and the
`full`-ordering that installs `shell` (mise-shim PATH, theme) before `editors`.

## Curated VS Code extension list (`modules/vscode/extensions.txt`, data)
Language-agnostic editor quality + theme (per-language sets → dev-stacks, Spec 7):
```
editorconfig.editorconfig
esbenp.prettier-vscode
eamodio.gitlens
usernamehw.errorlens
gruntfuggly.todo-tree
tamasfe.even-better-toml
redhat.vscode-yaml
mikestead.dotenv
catppuccin.catppuccin-vsc
catppuccin.catppuccin-vsc-icons
```

## `fresh` config (`~/.config/fresh/config.json`)
Single JSON file (context7 `/sinelaw/fresh`). Base template `config.base.json` (module-owned,
seeded if absent — see research D4):
```jsonc
{
  "version": 1,
  "theme": "catppuccin-mocha",
  "editor": { "tab_size": 4, "format_on_save": true },
  "lsp": { }                       // ← filled by fresh_lsp_provision (jq-merge)
}
```
`fresh_lsp_provision` adds, per language, an `lsp.<lang>` object:
```jsonc
"lsp": { "python": { "command": "<abs path from `mise which`>", "args": ["--stdio"], "enabled": true } }
```

## Always-on base set (`modules/fresh-lsp/servers.base.tsv`, applied by `editors`)
| lang | fresh command | mise backend:tool@pin | args |
|---|---|---|---|
| markdown | marksman | `aqua:artempyanykh/marksman@<pin>` | — |
| toml | taplo | `cargo:taplo-cli@<pin>` | `lsp stdio` |
| bash | bash-language-server | `npm:bash-language-server@<pin>` | `start` |
| json/yaml | yaml-language-server | `npm:yaml-language-server@<pin>` | `--stdio` |

## Stack → server/formatter map (DATA for dev-stacks / Spec 7 — documented here, NOT installed by `editors`)
| stack profile | language server(s) | formatter | mise backend(s) |
|---|---|---|---|
| laravel | intelephense | pint | `npm:`, `composer`-provided pint |
| dotnet | csharp-ls | csharpier | `dotnet`-tool / `aqua:` |
| python | basedpyright | ruff | `npm:basedpyright`, `pipx:`/`aqua:ruff` |
| web | typescript-language-server, vscode-eslint-language-server, tailwindcss-language-server | prettier | `npm:` |
| devops | terraform-ls | (rustfmt/gofmt as needed) | `aqua:`/`github:` |
Each stack module (Spec 7) calls `fresh_lsp_provision` for its rows, reusing `lib/fresh.sh`.

## State / verify per module
| Module | Verify (END state) |
|---|---|
| `vscode` | `command -v code` AND every `extensions.txt` ID present in `code --list-extensions` |
| `fresh` | `command -v fresh` |
| `fresh-lsp` | every `servers.base.tsv` tool installed in mise AND its `lsp.<lang>` entry present in `config.json` |

## `lib/fresh.sh` contract
`fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin> [args…]`:
1. `mise use -g <backend:tool@pin>` (idempotent; pin recorded).
2. `abs=$(mise which <fresh-command>)` (fail naming the tool if unresolved).
3. jq-merge `{lsp:{<lang>:{command:$abs,args:[args…],enabled:true}}}` into `~/.config/fresh/config.json`,
   preserving all other keys; idempotent (re-merge → byte-identical for the `lsp` subtree).

## Validation rules (from FRs)
| Rule | Source |
|---|---|
| `editors` profile = vscode+fresh+fresh-lsp; depends on base+shell | FR-001, FR-002 |
| VS Code installed + launchable + non-interactive extension mgmt | FR-003 |
| curated baseline extensions installed, only-missing, idempotent | FR-004, FR-006 |
| fresh installed on PATH, with documented fallback | FR-005 |
| fresh servers/formatters scoped to selected stacks (structural) | FR-007 |
| always-on base set provisioned regardless of stacks | FR-008 |
| each server/formatter is a mise-managed pinned tool (runtime from mise) | FR-009, FR-010 |
| fresh wired so servers→completion/diagnostics, formatters→format-on-save | FR-011 |
| lsp merge preserves dotfile/base keys, idempotent | FR-012 |
| unsupported-OS / editor-missing → named failure (no silent skip) | FR-013 |
| add extension / stack-mapping = data change, not engine | FR-014 |
| zero interactive prompts | FR-015 |

## Ordering (depsort via requires)
```
mise (base)  ─┐
fresh         ├─→ fresh-lsp
vscode        ┘ (independent)
shell (full-ordering: mise-shim PATH + theme) before editors
non-Fedora: engine reports each unsupported (no fedora-key match)
```
