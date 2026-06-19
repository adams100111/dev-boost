# Quickstart / Validation: secrets-and-auth

Proves the feature end-to-end with **no real network and no real secrets** (the same
hermetic approach the bats suite uses). See `contracts/` for exact interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3` available (engine deps).
- `age`, `openssh`, `curl` may be **stubbed** (the suite provides PATH stubs under
  `tests/fixtures/secrets/bin/`). No GitHub account needed.

## Run the tests (primary validation)
```bash
bats tests/secrets.bats tests/github.bats tests/ssh-setup.bats tests/doctor.bats
# or the whole suite:
bats tests/
```
Expected: all green, including idempotency (second run = skip), missing/undecryptable
bundle cases, and upload success/duplicate/failure cases. No test performs real network
I/O (asserted by inspecting the curl-stub call log).

## Manual smoke (optional, with a real age key + scratch HOME)
```bash
# 1. make a throwaway identity + bundle
age-keygen -o /tmp/age-key.txt
jq -n '{GIT_USER:"Test Dev",GIT_EMAIL:"t@example.com",GITHUB_PAT:"ghp_dummy"}' \
  | age -e -i /tmp/age-key.txt -o /tmp/secrets.age   # (recipient from the key)

# 2. point the engine at a scratch HOME and the bundle
export HOME=/tmp/devboost-home && mkdir -p "$HOME"
export DEVBOOST_SECRETS=/tmp/secrets.age DEVBOOST_SECRETS_KEY=/tmp/age-key.txt

# 3. preflight + install just these modules (by explicit module token; the `base`
#    profile is defined later in the base-profile spec, so install the modules directly)
./bin/devboost doctor
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/tests/fixtures/secrets/profiles.toml" \
  ./bin/devboost install secrets ssh-setup
```
Expected outcomes:
- `~/.gitconfig` has user.name/email + `credential.helper=store`.
- `~/.git-credentials` exists, mode `600`, contains a `github.com` line.
- `~/.ssh/id_ed25519{,.pub}` exist; `~/.ssh/config` has the hardened devboost block.
- Re-running `install` reports both modules **skipped** (idempotent).
- No prompt appeared at any point.
- `git ls-files` shows no `*.age`, no key, no credentials.

## Tear down
```bash
rm -rf /tmp/devboost-home /tmp/age-key.txt /tmp/secrets.age
```
