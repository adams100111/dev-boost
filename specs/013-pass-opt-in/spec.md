# Feature Specification: pass-opt-in

**Feature Branch**: `013-pass-opt-in` | **Created**: 2026-06-21 | **Status**: Draft

**Input**: "pass-opt-in — security-cli opt-in profile: pass CLI password-store (GPG+git), complementing Bitwarden."

## User Scenarios & Testing *(mandatory)*

An opt-in CLI password store for users who want a scriptable, git-backed secret store (`$(pass show …)`
in shell) alongside the default Bitwarden GUI. Off the critical path — NOT in `full`. Like `secrets`
provisions `age`, this provisions a GPG key + an initialized `pass` store for **unattended** decrypt
(design §11). Data modules (zero engine touch).

### User Story 1 - pass is available (Priority: P1)
Selecting `security-cli` installs the `pass` CLI.
**Independent Test**: install `pass` module (stubbed dnf) → `command -v pass` verifies; idempotent; unsupported-OS.
**Acceptance**:
1. **Given** `--profile security-cli`, **When** installed, **Then** `pass` is installed and verifies; re-run no-op; non-Fedora → unsupported.

### User Story 2 - The store is provisioned for unattended use (Priority: P2)
A GPG key is provisioned (passphrase-less / keyring-unlocked) and the password store is initialized
(`pass init <gpg-id>`), optionally cloning an existing password-store git repo — so `pass show`/`pass git`
work with no prompts, analogous to how `secrets` provisions `age`.
**Independent Test**: run `pass-store` (stubbed gpg/pass/git) → a GPG key exists (generated only if absent),
`pass init <gpg-id>` ran, and (if `$DEVBOOST_PASS_REPO` set) the store repo was cloned to `~/.password-store`;
verify: `~/.password-store/.gpg-id` present; idempotent.
**Acceptance**:
1. **Given** no GPG key, **When** `pass-store` runs, **Then** it generates a passphrase-less key (batch) and runs `pass init <gpg-id>`.
2. **Given** a key already present, **When** re-run, **Then** it does not regenerate (idempotent).
3. **Given** `$DEVBOOST_PASS_REPO`, **When** `pass-store` runs, **Then** it clones that repo into `~/.password-store`; absent → just `pass init`.

### Edge Cases
- `security-cli` is opt-in — NOT in `full` and NOT in the zero-touch path (needs the GPG key provisioned).
- GPG key passphrase-less is acceptable for this opt-in store (documented), mirroring the `secrets`/vault model; gnome-keyring-unlocked is the documented alternative.
- Re-running must not regenerate the key or re-init a populated store (idempotent).
- All gpg/pass/git operations are stubbed in tests — no real keyring/secret mutation.

## Clarifications
### Session 2026-06-21 (self-resolved, design §11 oracle)
- Q: profile members? → A: `security-cli = ["pass","pass-store"]` (pass = CLI; pass-store = GPG+store
  provisioning). Opt-in, NOT in full. [FR-001,003]
- Q: GPG/unattended model? → A: passphrase-less key generated only if absent (batch), `pass init <gpg-id>`,
  optional clone of `$DEVBOOST_PASS_REPO` → ~/.password-store; analogous to secrets/age; documented. [FR-002]
- Q: scope? → A: data modules only; zero engine touch; complements (does NOT replace) Bitwarden. [Assumptions]

## Requirements *(mandatory)*
- **FR-001**: A `pass` module MUST install the `pass` CLI (Fedora-only, idempotent, verify `command -v pass`).
- **FR-002**: A `pass-store` module (requires `pass` + `secrets`) MUST provision a GPG key for unattended
  decrypt (passphrase-less; generate only if absent), run `pass init <gpg-id>`, and clone
  `$DEVBOOST_PASS_REPO` into `~/.password-store` when set; verify `~/.password-store/.gpg-id` present; idempotent.
- **FR-003**: A `security-cli` profile MUST = `["pass","pass-store"]`, opt-in (NOT in `full`).
- **FR-004**: Zero engine touch; complements (not replaces) the Bitwarden GUI; built test-first; stub
  gpg/pass/git — no real keyring/secret mutation; suite stays green.

## Success Criteria *(mandatory)*
- **SC-001**: `pass` installs + verifies; `security-cli` resolves; not in `full`.
- **SC-002**: After `pass-store`, the store is initialized and usable unattended (`.gpg-id` present), key
  generated only when absent (idempotent).
- **SC-003**: Full suite stays green; all stub-only.

## Assumptions
- Design §11 is the oracle. `pass` complements Bitwarden (the default GUI in `apps`), never replaces it.
- Passphrase-less GPG key is acceptable for this opt-in store (documented), mirroring the secrets/vault model.
- `$DEVBOOST_PASS_REPO` (the password-store git remote) is provisioned out-of-band; absent → local-only init.
- Data modules only; no engine/full-profile change.
