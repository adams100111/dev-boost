# Phase 0 Research: secrets-and-auth

All spec clarifications were resolved in `/speckit-clarify`. The remaining unknowns
were plan-level (how to realize the behavior on the existing engine without changing
control flow). Decisions below.

## D1. Credential propagation across `bash -c` subshells

**Decision**: Propagate via durable on-disk artifacts the modules write, plus
on-demand re-decryption — not process env.

**Rationale**: `run_install` executes each module's install command with
`bash -c "$icmd"` (see `lib/install.sh`), a child process. Exported variables cannot
flow back to the engine or sideways to later modules. The credentials that later
modules actually need are already durable: `~/.gitconfig` (identity) and
`~/.git-credentials` (PAT for HTTPS) are written by the `secrets` module and read by
git natively for every later private clone. Anything needing the raw PAT
(`ssh-setup` now, `obsidian-sync` later) calls `lib/secrets.sh::secrets_pat`, which
re-decrypts the bundle on demand. Re-decrypt is cheap and stateless and avoids leaving
plaintext anywhere.

**Alternatives considered**:
- *Engine sources secrets before the loop and exports env* — would change engine
  control flow and make secrets a special-cased non-module; rejected (constitution §I).
- *Write decrypted bundle to a 0600 state file consumed by later modules* — adds a
  persistent plaintext-secret file (larger leak surface) for no gain over re-decrypt;
  rejected.

## D2. Escape-hatch execution contract (no engine change)

**Decision**: Module `install.sh` scripts source the engine libs themselves:
`source "$DEVBOOST_ROOT/lib/log.sh"`, `lib/secrets.sh`, `lib/github.sh`. The
install command string in `module.toml` is `bash "$DEVBOOST_ROOT/modules/<m>/install.sh"`.

**Rationale**: `bin/devboost` exports `DEVBOOST_ROOT`, `OS_DISTRO`, `OS_FAMILY`,
`OS_ARCH`; `bash -c` inherits them, so `install.sh` can locate and source libs without
the engine injecting helpers. This keeps `run_install` unchanged while still giving the
escape hatch the logging/helpers the design §3.2 describes. The richer engine-injected
helper set (`have`, `as_root`, `dnf_install`) is not required by this feature; a minimal
`have()`/`ensure_pkg()` lives in `lib/secrets.sh` shared scope.

**Alternatives considered**: implement design §3.2 helper-injection in `run_install`
now — deferred; not needed here and would be an engine change. Captured as a future
note for the base-profile spec.

## D3. age decryption — keyfile only (v1)

**Decision**: `age -d -i <identity-keyfile> <bundle.age>` → JSON on stdout, parsed by
`jq`. Identity key file located at `$DEVBOOST_SECRETS_KEY` or a default next to the
bundle; bundle located at `--secrets PATH` → `$DEVBOOST_SECRETS` → default USB/bootstrap
path. No passphrase path (clarify Q3).

**Rationale**: Fully non-interactive, matches design §7. jq parsing (clarify Q1) avoids
the shell-eval injection risk of sourcing a dotenv file.

**age availability**: ensured by entrypoint/`doctor` preflight; install key per OS —
`fedora: dnf install -y age`, `debian: apt-get install -y age`, `macos: brew install age`.

## D4. GitHub REST API surface

**Decision**: Use `curl` against:
- `POST /user/keys` (title + key) to register the machine SSH key; pre-check with
  `GET /user/keys` and match on title `devboost:<hostname>` **or** identical key body
  to guarantee idempotency.
- `POST /repos/{owner}/{repo}/keys` (title, key, `read_only`) for the reusable
  deploy-key helper (consumed later by obsidian-sync); same GET pre-check.
Auth header `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2022-11-28`.

**Rationale**: Standard, stable endpoints; title-based de-dupe gives clean idempotency
without storing remote IDs locally.

**Failure handling**: non-2xx → `lib/github.sh` returns non-zero with the parsed
message; the `ssh-setup` module treats upload failure as non-blocking (warn + state
marker absent) unless the engine ran with `--strict`.

## D5. Idempotency markers

**Decision**:
- `secrets` verify: git identity set **and** `~/.git-credentials` contains a
  `github.com` entry.
- `ssh-setup` verify: `~/.ssh/id_ed25519.pub` exists **and** a local marker
  `~/.local/state/devboost/ssh-key-registered` exists (written only after a confirmed
  registration / detected pre-existing remote key).

**Rationale**: verify must be fast and offline-safe; the marker records the
network-confirmed fact so a re-run skips without another API call, while the upload
function still de-dupes remotely when it does run.

## D6. Testing strategy (no network, no real secrets)

**Decision**: bats with PATH-prepended stub executables for `age`, `curl`,
`ssh-keygen`, and (where needed) `git`, plus `DEVBOOST_SECRETS*`, `HOME`, and
`OS_*` overrides pointing at per-test temp dirs.
- `age` stub: echoes a fixture JSON bundle.
- `curl` stub: returns canned `GET`/`POST` responses keyed by URL/args to exercise
  success, already-registered (duplicate), and HTTP-error paths.
- `ssh-keygen` stub: writes deterministic fake key files.
Assertions check real resulting files/permissions and the exact API calls attempted
(recorded by the curl stub to a log file).

**Rationale**: Honors constitution §V (real-behavior assertions) while keeping tests
hermetic and fast; mirrors the engine-core test approach already in `tests/`.

## Outcome

No unresolved `NEEDS CLARIFICATION`. Ready for Phase 1 design artifacts.
