# Implementation Plan: secrets-and-auth

**Branch**: `001-secrets-and-auth` | **Date**: 2026-06-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-secrets-and-auth/spec.md`

## Summary

Provide the unattended credential foundation as **data + escape-hatch modules over the
existing engine**, with no change to the engine's control flow. Two folder modules
(`modules/secrets`, `modules/ssh-setup`) carry `module.toml` + `install.sh`; two new
sourced libraries (`lib/secrets.sh`, `lib/github.sh`) hold the reusable logic. The
`secrets` module decrypts an age-encrypted JSON bundle with a key file, configures git
identity, and seeds `git credential.helper store` so private HTTPS clones work; the
`ssh-setup` module generates an ed25519 key and registers it with GitHub via the REST
API under the title `devboost:<hostname>`. Because `run_install` runs each module in a
`bash -c` subshell, credentials are propagated **through durable on-disk artifacts the
modules themselves write** (`~/.gitconfig`, `~/.git-credentials`) and via on-demand
re-decryption (`lib/secrets.sh`) — never through process env, and never by writing the
plaintext bundle to disk. Built test-first with bats, mocking `age`/`curl`/`ssh-keygen`
via PATH stubs so no real network or real secrets are needed.

## Technical Context

**Language/Version**: Bash (engine + modules); system `python3` (≥3.11 `tomllib`, already used) for TOML; `jq` for JSON.
**Primary Dependencies**: `age` (decrypt), `openssh` (`ssh-keygen`), `curl` (GitHub REST API), `git`. All are leaf tools invoked by escape-hatch scripts; the engine gains no new runtime dependency.
**Storage**: User dotfiles only — `~/.gitconfig`, `~/.git-credentials` (0600), `~/.ssh/id_ed25519{,.pub}` (0600/0644), `~/.ssh/config`, and a state marker under `~/.local/state/devboost/`. No database.
**Testing**: `bats` (existing harness in `tests/`), with PATH stub binaries for `age`, `curl`, `ssh-keygen`, `git`, and `DEVBOOST_*` env overrides. No real network calls (constitution §V).
**Target Platform**: Fedora 44 reference (full support); `debian`/`macos` thinner via additional `[install]` keys where they differ (e.g. installing `age`).
**Project Type**: Single-project CLI/bootstrap engine (Bash). Source at repo root (`lib/`, `modules/`, `bin/`, `tests/`).
**Performance Goals**: Not latency-sensitive; whole feature completes in seconds. Decrypt is O(one small file).
**Constraints**: Strictly unattended (no prompts); no decrypted secret in git or world-readable; idempotent/verify-guarded; engine control flow unchanged.
**Scale/Scope**: 2 modules, 2 libs, a `doctor`/entrypoint preflight extension, ~4 bats files. First real `modules/` and first escape-hatch usage in the repo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS (with one justified touch). New capability ships as modules (data + `install.sh`) + sourced libs. `run_install`/`depsort`/`module.sh` are **not** modified. The only engine edits are the `doctor`/entrypoint **preflight** (age presence + delegating a secrets check to `lib/secrets.sh::secrets_doctor`), which is preflight responsibility the design assigns to `doctor`/the entrypoint (design §2, §4), not per-module branching. Recorded in Complexity Tracking.
- **II. Idempotent & Verify-Guarded** — PASS. Each module declares a top-level `verify` that detects already-satisfied end-state; re-runs do only what is missing; the GitHub upload de-dupes by key title and public-key value.
- **III. Reproducible — Repo is Source of Truth** — PASS. The encrypted bundle and all key material stay gitignored; nothing decrypted is committed; no version pins are introduced by this feature.
- **IV. Unattended by Default** — PASS. Keyfile decrypt (no passphrase prompt), SSH key uploaded via API (no paste-and-wait), failures in the upload are non-blocking unless `--strict`.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. Every lib function and module behavior is specified by a failing bats test first; external tools are stubbed; assertions check real state.
- **VI. Cross-OS via Data** — PASS. OS differences (installing `age`) live in `[install].<os>` keys; reference is Fedora; helper logic is OS-agnostic.

**Security constraints** — `bash -c` trust model preserved; secret decrypted only into process memory / consumed immediately; `~/.git-credentials` and private key are `chmod 600`; `.gitignore` excludes secret/key artifacts.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-secrets-and-auth/
├── plan.md              # this file
├── research.md          # Phase 0 — decisions & rationale
├── data-model.md        # Phase 1 — entities, files, state
├── quickstart.md        # Phase 1 — runnable validation guide
├── contracts/           # Phase 1 — module manifests + lib API + CLI behavior
│   ├── module-secrets.md
│   ├── module-ssh-setup.md
│   ├── lib-secrets.md
│   ├── lib-github.md
│   └── doctor-preflight.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
lib/
├── secrets.sh           # NEW — locate + age-decrypt bundle; expose git_user/email/pat; secrets_doctor
└── github.sh            # NEW — PAT-authenticated GitHub REST helpers (upload SSH key, add deploy key)

modules/                 # NEW directory (first real modules)
├── secrets/
│   ├── module.toml      # name, requires=[], verify, [install] → install.sh
│   └── install.sh       # ensure age; decrypt; git identity; seed credential store
└── ssh-setup/
    ├── module.toml      # name, requires=["secrets"], verify, [install] → install.sh
    └── install.sh       # gen ed25519 if absent; upload pubkey; harden ~/.ssh/config

bin/devboost             # EDIT — doctor: age presence + secrets_doctor preflight
install.sh               # EDIT — entrypoint preflight guarantees age (alongside python3, jq)
.gitignore               # EDIT — ensure *.age, key files, credential artifacts excluded

tests/
├── secrets.bats         # NEW — lib/secrets.sh + modules/secrets (stubbed age/git)
├── github.bats          # NEW — lib/github.sh (stubbed curl; success/duplicate/failure)
├── ssh-setup.bats       # NEW — modules/ssh-setup (stubbed ssh-keygen/curl)
├── doctor.bats          # NEW — doctor secrets+age preflight
└── fixtures/secrets/    # NEW — test keyfile + sample bundle plaintext + stub bins
```

**Structure Decision**: Single-project Bash engine. New code is additive: two sourced
libs under `lib/`, the first two real modules under `modules/`, focused bats files
under `tests/`. Engine control-flow files (`lib/install.sh`, `lib/depsort.sh`,
`lib/module.sh`, `lib/profile.sh`) are untouched; only `bin/devboost` (doctor preflight)
and the `install.sh` entrypoint preflight change, both within their existing preflight
responsibility.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Engine touch: `doctor` + entrypoint preflight gain age/secrets checks | The design assigns secrets-presence and the python3/jq/**age** guarantee to `doctor`/the entrypoint (§2, §4); a recovery run must fail fast when the bundle is absent | Putting the check only inside the module would let `install` start, partially run, then fail mid-way — violating the fail-fast preflight contract. The check is generic (delegates to `lib/secrets.sh::secrets_doctor`), not per-module branching, so Engine+Data separation holds. |
