# Quickstart / Validation: editors

Proves the `editors` profile end-to-end **hermetically** (no real installs/network/editor
launch) via the bats stub harness. See `contracts/` for exact interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3`. Specs 1–5 merged (base/mise/shell on `main`).
- Package/editor tooling (`dnf`, `rpm`, `code`, `mise`, `curl`, `cargo`) is **stubbed** by
  `tests/fixtures/base/`. Real `jq` runs the `config.json` merge against a temp file. No root,
  no network, no editor launch.

## Run the tests (primary validation)
```bash
bats tests/vscode.bats tests/fresh.bats tests/fresh-lsp.bats tests/profiles.bats
# or the whole suite:
bats tests/
```
Expected: all green — MS repo + `code` install + only-missing extensions + idempotent skip;
fresh primary install and each fallback + all-fail→named die; base-config seed (no clobber);
`fresh_lsp_provision` mise-install + `mise which` + idempotent `lsp` merge preserving other
keys; editor-missing→named fail; unsupported-OS path. No real installs.

## Resolution smoke (list only)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost list --profile editors
```
Expected: `vscode`/`fresh`/`fresh-lsp` (+ transitive `mise`), `fresh` and `mise` before
`fresh-lsp`, no cycle.

## Manual smoke (optional, real Fedora-Workstation VM)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile editors
```
Expected: `code` installed from the MS repo with the curated extensions
(`code --list-extensions` shows them); `fresh` on PATH; `~/.config/fresh/config.json` has the
base theme + an `lsp` block for the always-on base languages (markdown/toml/bash/json-yaml),
each `command` an absolute mise path; opening a `.md`/`.toml`/`.sh` file in `fresh` gives
completion; re-run reports every module skipped; `git ls-files` shows no secrets.

## Tear down
Throwaway VM only; no host changes via the test stubs.
