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

## Conventions
TDD (test-first), idempotent, verify-guarded, no prompts, pin versions in module data.
