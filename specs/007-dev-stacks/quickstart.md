# Quickstart / Validation: dev-stacks

Proves the seven stack profiles **hermetically** (no real installs/network/containers/SDK) via the
bats stub harness. See `contracts/` + `research.md` (context7-verified pins, 2026-06).

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3`. Specs 1–6 merged (base/mise/docker/editors on `main`).
- All installers stubbed by `tests/fixtures/base/`: `ddev`, `dotnet`, `sdkmanager`/cmdline-tools,
  `uv`, `npx`/`expo`, plus existing `mise`/`dnf`/`rpm`/`curl`/`docker`. Real `jq` for fresh merges.

## Run the tests (primary validation)
```bash
bats tests/python-stack.bats tests/web-stack.bats tests/laravel-stack.bats \
     tests/dotnet-stack.bats tests/data-stack.bats tests/devops-stack.bats \
     tests/react-native-stack.bats tests/profiles.bats
# or the whole suite:
bats tests/
```
Expected: all green — each stack's toolchain install attempted with the verified pin; fresh
servers wired (where applicable); template present; idempotent re-run no-op; unsupported-OS
failure; stack isolation. No real installs.

## Resolution smoke (list only) — per stack
```bash
for s in python web laravel dotnet data devops react-native; do
  DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
    ./bin/devboost list --profile "$s"
done
```
Expected: each resolves without cycle; `*-lsp` after its toolchain + `mise`/`fresh`.

## Manual smoke (optional, real Fedora VM with base+editors)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile python   # then web, laravel, dotnet, data, devops, react-native
```
Expected (examples): `uv --version` works + `templates/python` present; `mise which node` = 22 +
ts/eslint/tailwind wired in `~/.config/fresh/config.json`; `ddev version` works; `dotnet --list-sdks`
shows 10.* + `aspire --help`; `docker compose -f templates/data/compose.yaml up -d` brings up
postgres18 + valkey + dbgate (data persists across restart); `tofu version`/`kubectl`/`helm`/`k9s`;
`adb --version` + Android SDK 35 + `npx create-expo-app` works. Re-running install = all skipped.
`git ls-files` shows no secrets.

## Tear down
Throwaway VM only; the test stubs make no host changes. `docker compose ... down -v` for data.
