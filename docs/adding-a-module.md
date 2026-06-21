# Adding a module (or an OS)

## Add a tool — one file
```sh
devboost add <name>            # scaffolds modules/<name>/module.toml from the template
devboost add <name> --folder   # also scaffolds an install.sh escape-hatch
```
Fill the manifest:
```toml
name     = "ripgrep"
category = "cli"
requires = []                  # other module names (topo-sorted before this one)
profiles = ["cli"]
verify   = "rg --version"      # success ⇒ already installed ⇒ skipped (idempotency guard)
[install]
fedora = "dnf install -y ripgrep"
```
Then add `ripgrep` to a profile in `profiles.toml` and commit. Verify:
```sh
devboost list --profile cli   # see it resolve
bats tests/                   # keep green (add a test for non-trivial modules)
```

## Escape hatch (complex tools)
`modules/<name>/install.sh` (sources `lib/log.sh`+`lib/pkg.sh`; `set -Eeuo pipefail`; idempotent;
`log_ok`/`die`) + `verify.sh`. Reference it from `[install].fedora = "bash \"$DEVBOOST_ROOT/modules/<name>/install.sh\""`.

## Add an OS — one key
Add `[install].<os>` (e.g. `ubuntu`, `macos`, `windows`) to the affected modules. `doctor` reports
coverage gaps. No engine change required.

## Conventions
TDD (test-first), idempotent, verify-guarded, no prompts, pin versions in module data.
