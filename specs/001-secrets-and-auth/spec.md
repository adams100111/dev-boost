# Feature Specification: secrets-and-auth

**Feature Branch**: `001-secrets-and-auth`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "secrets-and-auth — the unattended authentication foundation (design doc §7 boot sequence steps 1-4, §11 phase 2, roadmap Spec 1)."

## Overview

The bootstrap must reach a working, authenticated developer machine with **zero
interactive prompts**. This feature provides the credential foundation every later
subsystem depends on: it turns a pre-provisioned, encrypted secret into a configured
git identity, working private-repo access over HTTPS, and a real SSH key registered
with GitHub — all without pausing for human input. It is delivered as two engine
modules (`secrets`, `ssh-setup`) plus a GitHub API helper library reused by later
modules (e.g. the notes-vault deploy key).

## Clarifications

### Session 2026-06-19

- Q: What format should the decrypted secrets bundle use? → A: A JSON document, parsed with jq (no shell evaluation of the secret) — chosen for safe structured parsing (avoids the code-execution risk of sourcing a dotenv file) and good editing DX, reusing the already-required jq dependency.
- Q: How should the machine's GitHub SSH key be titled (idempotency identifier)? → A: `devboost:<hostname>` — namespaced, stable, human-readable; duplicate detection matches on this exact title.
- Q: Which decryption methods should v1 support? → A: Keyfile only (age identity file on the USB / explicit path); the passphrase fallback is dropped from v1 to keep the flow strictly unattended.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Credentials available unattended (Priority: P1)

An operator boots a fresh machine and runs the bootstrap, having placed an encrypted
secret bundle and its decryption key where the engine can find them (the USB, or an
explicit path). Without typing anything, the engine unlocks the bundle, configures the
git identity, and makes the access token usable so that private repositories clone
immediately over HTTPS.

**Why this priority**: Nothing else in the platform can proceed unattended without
credentials. Private dotfiles, the notes vault, and templates all clone using this.
This story alone is the minimum viable foundation.

**Independent Test**: Provide a fixture encrypted bundle + key, run the secrets step,
and confirm (a) the three identity values are available to the engine, (b) git is
configured with the right name/email, (c) a private-HTTPS clone is authorized — all
with no prompt and no network needed for the unlock itself.

**Acceptance Scenarios**:

1. **Given** an encrypted bundle and a key file at the default location, **When** the secrets step runs, **Then** the git user name, email, and access token become available to the engine and git is configured accordingly, with no prompt.
2. **Given** an explicit `--secrets PATH`, **When** the secrets step runs, **Then** it uses that bundle instead of the default location.
3. **Given** the secrets step already ran successfully, **When** it runs again, **Then** it is a no-op (idempotent) and reports already-configured.
4. **Given** a configured token, **When** a private HTTPS repository is cloned, **Then** the clone succeeds without prompting for username or password.

---

### User Story 2 - SSH key registered with GitHub automatically (Priority: P2)

The machine ends the bootstrap with its own SSH key already registered on the
operator's GitHub account, generated and uploaded automatically — replacing the old
"display the key and wait for the human to paste it into GitHub" pause.

**Why this priority**: SSH access is needed for ongoing development and for the
deploy-key flow later, but the platform can already function on HTTPS+token from
Story 1, so this is important rather than critical.

**Independent Test**: With a generated (or pre-existing) key and a mocked GitHub API,
run the ssh-setup step and assert the public key is submitted exactly once, the step
is skipped when the key is already registered, and the run never blocks on input.

**Acceptance Scenarios**:

1. **Given** no SSH key exists, **When** ssh-setup runs, **Then** an ed25519 keypair is created and its public key is uploaded to the account.
2. **Given** a key already registered with the account, **When** ssh-setup runs again, **Then** no duplicate is created or uploaded (idempotent).
3. **Given** the key-upload network call fails, **When** ssh-setup runs in the default (non-strict) mode, **Then** it records the failure, continues the bootstrap, and the machine still has a usable token-based path; in strict mode it aborts with a clear message.
4. **Given** ssh-setup completes, **When** the SSH config is inspected, **Then** it references the ed25519 key with hardened defaults and never paused for human input.

---

### User Story 3 - Preflight and secret safety (Priority: P3)

Before doing any work, the operator can confirm the machine is ready: the
environment check reports whether a secret bundle is present and decryptable. At no
point is a decrypted secret written into version control or left readable by other
users.

**Why this priority**: Improves diagnosability and enforces the security guarantee,
but the happy path in Stories 1–2 already implies safe handling; this story makes it
explicit and checkable.

**Independent Test**: Run the environment check with and without a valid bundle and
assert the reported status; inspect produced files and the repository ignore rules to
confirm no plaintext secret is tracked or world-readable.

**Acceptance Scenarios**:

1. **Given** a present, decryptable bundle, **When** the environment check runs, **Then** it reports secrets ready.
2. **Given** a missing or undecryptable bundle, **When** the environment check runs, **Then** it reports the specific problem (missing vs cannot-decrypt) and the bootstrap can refuse to start the credentialed steps.
3. **Given** any successful run, **When** the workspace is inspected, **Then** no decrypted secret, token, or private key is tracked by version control, and credential/key files are not readable by other users.

### Edge Cases

- Bundle present but the decryption key is missing or wrong → reported as cannot-decrypt, distinct from missing.
- Identity values partially present in the bundle (e.g. token but no email) → reported as an incomplete-bundle failure naming the missing field, not a silent partial configuration.
- Token present but lacking the permission to register a key → upload fails; handled by Story 2 scenario 3 (warn-and-continue / strict-abort).
- A pre-existing SSH key with a different/unknown provenance → not overwritten; the existing key is reused and its public half is what gets registered.
- The decryption tool is not installed on the fresh machine → the step ensures it is available before attempting to decrypt.
- No network at all → unlock and git configuration still succeed; only the key-upload convenience is deferred (warn-and-continue).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST locate the encrypted secret bundle from a default location and from an explicit operator-supplied path, preferring the explicit path when given.
- **FR-002**: The system MUST decrypt the bundle non-interactively using a key file (zero-touch); the key file is the only supported unlock method in v1 (no passphrase fallback), so the unlock never requires interactive input.
- **FR-003**: The system MUST read the decrypted bundle as a structured JSON document, extracting a git user name, a git email, and a GitHub access token, parsing it without shell evaluation of its contents, and MUST fail with a message naming any missing required field rather than configuring partially.
- **FR-004**: The system MUST configure the machine's git identity (name, email) and MUST seed credential storage with the access token so that private HTTPS clones succeed without prompting.
- **FR-005**: The system MUST generate an ed25519 SSH keypair only if one does not already exist, and MUST never overwrite an existing key.
- **FR-006**: The system MUST register the SSH public key with the operator's GitHub account via its API under the title `devboost:<hostname>`, MUST NOT create a duplicate when a key with that title (or the same public key) is already registered, and MUST complete without blocking on human input.
- **FR-007**: The system MUST treat key registration as non-blocking in the default mode (record failure, continue) and MUST abort on failure only when strict mode is requested.
- **FR-008**: The system MUST apply hardened SSH client configuration that references the ed25519 key with sane defaults.
- **FR-009**: Each module MUST be idempotent and verify-guarded: a verify check determines already-satisfied state and is evaluated before any install action; re-running performs only what is missing.
- **FR-010**: The environment check MUST report secret-bundle readiness, distinguishing "missing" from "present but cannot decrypt".
- **FR-011**: The system MUST ensure the decryption tool is available before attempting decryption, installing it if absent.
- **FR-012**: The system MUST NOT write any decrypted secret, token, or private key into version control, and MUST keep credential and private-key files unreadable by other users.
- **FR-013**: The system MUST expose a reusable capability to register a repository-scoped deploy key on a named repository via the GitHub API, for later subsystems to consume.
- **FR-014**: A failure in any step MUST name the module and the exact operation that failed (consistent with the platform's failure-reporting rule).
- **FR-015**: OS-specific actions (e.g. ensuring the decryption tool) MUST be expressed as per-OS data resolved by the platform precedence, with the reference OS fully supported and others allowed to be thinner.

### Key Entities *(include if feature involves data)*

- **Encrypted secret bundle**: the at-rest, version-control-excluded artifact carrying the operator's credentials; unlocked with a separate decryption key or passphrase.
- **Decryption key / passphrase**: the separately-held unlock material; the key-file form enables fully zero-touch operation.
- **Identity credentials**: git user name, git email, and a GitHub access token extracted from the bundle.
- **SSH keypair**: the machine's ed25519 private/public key; the public half is the artifact registered with GitHub.
- **Registered GitHub key**: an account-level authentication key for the machine, titled `devboost:<hostname>`, and — separately — a repository-scoped deploy key (for later per-repo automation).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a fresh machine with the bundle in place, the credential foundation is established with **zero interactive prompts**.
- **SC-002**: After the run, cloning a private repository over HTTPS succeeds on the first attempt without any credential prompt.
- **SC-003**: After the run, the operator's GitHub account lists exactly one registered key for this machine, and re-running adds none.
- **SC-004**: Re-running the entire feature changes nothing and reports all steps already-satisfied (full idempotency).
- **SC-005**: No decrypted secret, token, or private key is ever tracked by version control across any run (verifiable by inspection of tracked files and ignore rules).
- **SC-006**: With no network available, the unlock and git-identity outcomes still complete; only key registration is deferred with a recorded warning.
- **SC-007**: Automated tests cover the happy path, idempotency, the missing/undecryptable-bundle cases, and the key-upload success/duplicate/failure cases without making real network calls.

## Assumptions

- Secrets are **pre-provisioned** before the run (operator responsibility); this feature consumes them and never prompts to create them (constitution §IV).
- The bundle's decrypted form is a JSON document carrying at least the git name, git email, and access token; additional keys may exist and are ignored. It is parsed structurally (no shell sourcing of the secret).
- v1 decrypts via an age identity key file only; passphrase-based unlock is out of scope for v1.
- The default bundle location is the platform's USB bootstrap area; the explicit-path option overrides it.
- The reference operating system is fully supported here; other operating systems are schema-supported and may provide a thinner path (constitution §VI).
- Network is available for the key-registration convenience in the normal case, but its absence must not block the credentialed core (Story 1).
- The access token carries sufficient permission to register a key; insufficient permission is handled as a non-blocking failure in the default mode.
- This feature is engine-adjacent and is therefore built test-first with the project's existing test harness, mocking the external API so no real network calls occur (constitution §V).
- "Registered key for this machine" is identified by a stable, machine-specific title so idempotency can be checked against the account's existing keys.
