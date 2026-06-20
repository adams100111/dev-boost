# Contract: `editors` profile entry

## `profiles.toml` (EDIT — add 1 entry, TOML-only, do NOT touch base/cli/shell/gnome/multimedia)
```toml
editors = ["vscode","fresh","fresh-lsp"]
```

## Depsort (via `requires`)
- `vscode` (`requires=[]`) — independent.
- `fresh` (`requires=[]`) — independent.
- `fresh-lsp` (`requires=["fresh","mise"]`) — sorts AFTER `fresh` and `mise` (base).
- No cycle. `mise` is pulled transitively from base; `shell` (mise-shim PATH + theme)
  precedes `editors` under the `full` ordering.

## Tests (`tests/profiles.bats`, extend)
- `profile_expand editors` membership/count = 3 (`vscode`,`fresh`,`fresh-lsp`), TOML-only.
- `devboost list --profile editors` (real `profiles.toml` + all `modules/`) depsorts without
  cycle, with `mise` before `fresh-lsp` and `fresh` before `fresh-lsp`.
