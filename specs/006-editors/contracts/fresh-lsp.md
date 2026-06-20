# Contract: `fresh-lsp` + `lib/fresh.sh` (US3)

Escape-hatch module sourcing `lib/log.sh`+`lib/pkg.sh`+`lib/fresh.sh`. `category="editors"`,
`requires=["fresh","mise"]`, only `[install].fedora`. Provisions the **always-on base set**
of `fresh` language intelligence; per-stack rows are added later by dev-stacks (Spec 7)
reusing the same helper.

## `lib/fresh.sh`
`fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin> [args…]`:
1. `mise use -g <backend:tool@pin>` — idempotent; the `@pin` is held in-repo in `servers.base.tsv`. (`mise use -g` records the resolved version into the user-global `~/.config/mise/config.toml`, as the base `mise` module does.)
2. `abs=$(mise which <fresh-command>)` — absolute path; if unresolved → `die` naming the tool.
3. jq-merge into `~/.config/fresh/config.json`:
   `{ "lsp": { "<lang>": { "command": <abs>, "args": [args…], "enabled": true } } }`,
   **preserving every other key** (`theme`, `editor`, `formatter`, `languages`, other `lsp.*`).
   Idempotent: re-running yields a byte-identical `lsp.<lang>` subtree.

## `fresh-lsp/install.sh`
1. If `~/.config/fresh/config.json` is **absent**, seed it from `modules/fresh-lsp/config.base.json`
   (theme `catppuccin-mocha`, editor defaults incl. `format_on_save`, empty `lsp`). Never
   overwrite an existing file.
2. For each row in `modules/fresh-lsp/servers.base.tsv` (lang, command, backend:tool@pin, args):
   call `fresh_lsp_provision`.
- `verify` (top-level): every base-set tool resolvable via `mise which` AND its `lsp.<lang>`
  entry present + enabled in `config.json`.
- `fresh` missing at provision time → `die` naming the editor (FR-013 edge case).

## Tests (`tests/fresh-lsp.bats`) — stubbed mise; real jq on a temp config
- Base seed: absent config → seeded from template (theme + `format_on_save` present, `lsp` empty).
- Base seed never clobbers: pre-existing config with a custom key is left intact.
- Provision: for a base-set row, `mise use -g <spec>` attempted; `mise which` resolved; the
  `lsp.<lang>` entry written with the absolute command + `enabled:true`.
- Merge preserves keys: after provisioning, `theme`/`editor`/any prior `lsp.*` remain.
- Idempotent: re-running provisioning leaves `config.json` unchanged (no dup, no rewrite) → verify GREEN.
- Scope: only `servers.base.tsv` languages are present; no stack-specific language (e.g. `python`
  via a stack row) appears, since no stack module ran.
- `fresh` missing → module FAILS naming the editor.
- Unsupported-OS → engine failure.
