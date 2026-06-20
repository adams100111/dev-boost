# Contract: 7 stack profile entries

## `profiles.toml` (EDIT — add 7 entries; do NOT touch base/cli/shell/gnome/multimedia/editors)
```toml
python       = ["uv","python-lsp"]
web          = ["web-runtimes","web-lsp"]
laravel      = ["ddev","laravel-lsp"]
dotnet       = ["dotnet-sdk","aspire","dotnet-lsp"]
data         = ["data-services"]
devops       = ["devops-tools","devops-lsp"]
react-native = ["web-runtimes","android-sdk","expo"]
```

## Depsort (via `requires`)
- `*-lsp` modules require `fresh`+`mise`(+toolchain) → sort after them; `mise`/`docker`/`fresh` come from base/editors transitively.
- `react-native` shares `web-runtimes` (node@22) with `web` — same module, installed once.
- No cycles. Non-Fedora → each module unsupported (no fedora-key match for the engine... note: these modules DO have fedora keys; unsupported is reported because the OS isn't fedora and there's no debian/default key).

## Tests (`profiles.bats`, extend)
- For each of the 7: `profile_expand <stack>` membership + count (TOML-only).
- `devboost list --profile <stack>` (real profiles.toml + modules/) depsorts without cycle; toolchain module ordered before its `*-lsp`; `mise`/`fresh` (transitive) before `*-lsp`.
- `react-native` includes `web-runtimes`.
