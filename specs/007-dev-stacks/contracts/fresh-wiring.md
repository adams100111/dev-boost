# Contract: per-stack fresh-LSP wiring (`*-lsp` modules + lib/fresh.sh)

## `lib/fresh.sh` (EDIT — additive, behavior-preserving)
Extract the jq-merge into a reusable primitive; `fresh_lsp_provision` now delegates to it:
```
fresh_lsp_wire <lang> <absolute-command> [args…]
  # jq-merge {lsp:{<lang>:{command:<abs>, args:[args…], enabled:true}}} into
  # ~/.config/fresh/config.json — idempotent, preserves all other keys.
  # die if config.json absent.
fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin> [args…]
  # mise use -g <spec> ; abs=$(mise which <fresh-command>) || die ; fresh_lsp_wire <lang> "$abs" args…
```
The editors test suite (tests/fresh-lsp.bats) MUST stay green (provision behavior unchanged).

## `*-lsp` modules (python-lsp / web-lsp / laravel-lsp / devops-lsp)
- `requires=["fresh","mise", <toolchain-module>]`; source `lib/log.sh`+`lib/fresh.sh`.
- `have fresh || die` (FR-014 edge). seed base config if absent (reuse fresh-lsp's seed, or require fresh-lsp present — simplest: require `fresh` and assume editors seeded config; if absent, seed from the editors base template path).
- loop `servers.tsv` (TAB: lang, cmd, spec, args) → `fresh_lsp_provision`.
- verify: each tsv tool `mise which`-resolvable AND `lsp.<lang>.enabled==true` in config.json.

## `dotnet-lsp` module (dotnet-tool servers — NOT mise)
- `requires=["fresh","dotnet-sdk"]`.
- `dotnet tool install -g csharp-ls` + `dotnet tool install -g csharpier` (each guarded by `command -v`).
- `fresh_lsp_wire csharp "$HOME/.dotnet/tools/csharp-ls"` (csharpier is the C# formatter, wired in `templates/dotnet/.fresh/config.json`).
- verify: `command -v csharp-ls` (or `~/.dotnet/tools/csharp-ls` present) AND `lsp.csharp.enabled==true`.

## Tests
- `mise use -g <spec>` attempted for each tsv row (assert log); `lsp.<lang>` written with absolute command + enabled; merge preserves other keys; idempotent re-run unchanged; `fresh` missing → named fail; non-selected stack's lang absent (scope). dotnet-lsp: `dotnet tool install` attempted + csharp wired. Reuse the editors hermetic-PATH trick where a real host tool would leak.
