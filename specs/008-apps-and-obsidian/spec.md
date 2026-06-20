# Feature Specification: apps-and-obsidian

**Feature Branch**: `008-apps-and-obsidian`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "apps-and-obsidian — the `apps` profile plus unattended Obsidian↔GitHub vault sync."

## User Scenarios & Testing *(mandatory)*

This feature delivers the workstation's everyday **GUI applications** and a **hands-off
notes vault** that is present, opens automatically, and round-trips to GitHub without the
user ever touching a credential, a remote, or a sync button. It is the realization of the
mission line *"GUI apps (Obsidian w/ GitHub sync, Bruno, Bitwarden, …)"* and design-doc §7.1.

### User Story 1 - Everyday GUI apps are installed (Priority: P1)

A developer selects the `apps` profile (or `full`) on a fresh machine. After the unattended
run, the desktop has the standard graphical toolkit ready to launch: a notes app (Obsidian),
an API client (Bruno), a password manager (Bitwarden), a screenshot tool (Flameshot), a local
file-transfer tool (LocalSend), and a media player (VLC) — each a curated, reproducible
install, with no app stores opened and no clicks required.

**Why this priority**: This is the standalone, immediately-valuable slice — a usable app
suite — and the prerequisite host for the Obsidian sync stories. It can ship and deliver
value even if the sync stories are not yet present.

**Independent Test**: Select only the `apps` profile on a clean (stubbed) environment; assert
each application is installed and its presence verifies; re-running is a no-op.

**Acceptance Scenarios**:

1. **Given** a Fedora machine with Flatpak + Flathub already configured (base profile), **When** the `apps` profile is installed, **Then** each of the six apps is installed from Flathub and each module's verify reports present.
2. **Given** the apps are already installed, **When** the profile is re-run, **Then** every app module skips (idempotent) and the run reports success with no reinstall.
3. **Given** a non-Fedora OS, **When** an `apps` module is attempted, **Then** the engine reports the module unsupported (no install attempted), per cross-OS-via-data.
4. **Given** the database GUI need, **When** a user looks for dbgate, **Then** it is **not** installed as a desktop app — it is provided as the persistent container shipped by the `data` stack — and this is documented (DBeaver remains an optional, non-default alternative).

---

### User Story 2 - The notes vault is present and opens automatically (Priority: P2)

On first boot the user's notes repository is already cloned to `~/Vault`, wired to GitHub over
a dedicated, repo-scoped key (no account-wide key, no plaintext token), and registered in
Obsidian so the app opens straight into the vault. `$VAULT_DIR` is on `PATH`-adjacent shell
environment and the vault is a recognized user directory.

**Why this priority**: A present, auto-opening vault is the core "it just works" outcome; it
depends on US1 (Obsidian installed) and on pre-provisioned secrets, so it follows P1.

**Independent Test**: With a stubbed GitHub API + git + ssh, run the sync module; assert a
repo-scoped deploy key is generated and registered (write), an SSH host alias isolates it,
the vault is cloned to `~/Vault`, and both the Flatpak and native Obsidian config files
register `~/Vault` as the open-on-launch vault.

**Acceptance Scenarios**:

1. **Given** a provisioned bootstrap token and git identity, **When** the sync module runs, **Then** a dedicated key `~/.ssh/notes_vault_ed25519` is generated (passphrase-less, unattended) and registered as a **write** deploy key on the notes-vault repository via the GitHub API.
2. **Given** the deploy key exists, **When** the module configures SSH, **Then** an isolated `~/.ssh/config` host alias points only that key at GitHub (`IdentitiesOnly`), and the vault is cloned to `~/Vault` over that alias.
3. **Given** Obsidian is installed (Flatpak), **When** the vault is registered, **Then** the Flatpak Obsidian config file lists `~/Vault` as a vault set to open; if a native install is present, its config is registered too.
4. **Given** the vault is already cloned and registered, **When** the module re-runs, **Then** it is a no-op (key not regenerated, deploy key not duplicated, configs not clobbered).
5. **Given** the bootstrap token / secrets are absent, **When** the module runs, **Then** it fails with a clear, named error and does not partially register a broken remote.

---

### User Story 3 - Edits sync live while Obsidian is open (Priority: P3)

While the user works in Obsidian, their notes pull on open and commit-and-sync automatically as
they edit — no manual git, no sync button — using the community Obsidian Git plugin, pre-seeded
with sensible single-user multi-device settings.

**Why this priority**: Live sync is the best day-to-day experience but is additive on top of a
present, registered vault (US2); the daily backstop (US4) covers the case where the plugin never
runs, so live-sync can land independently.

**Independent Test**: Run the sync module against a vault skeleton; assert the Obsidian Git
plugin's `data.json` is pre-seeded with the agreed settings and the plugin is enabled in
`community-plugins.json` — and that an existing user-edited `data.json` is never overwritten.

**Acceptance Scenarios**:

1. **Given** a freshly cloned vault without plugin settings, **When** the module runs, **Then** the Obsidian Git plugin `data.json` is seeded (auto-pull-on-boot, debounced commit-and-sync on change, periodic interval, pull-before-push, rebase sync, dated commit messages) and the plugin is listed enabled.
2. **Given** the vault already ships a committed `.obsidian/` with plugin settings, **When** the module runs, **Then** the existing settings are preserved (seed-if-absent only).
3. **Given** vault hygiene, **When** the vault is prepared, **Then** local-only UI state (`.obsidian/workspace*.json`) and `.trash/` are git-ignored so they do not create noisy or conflicting commits.

---

### User Story 4 - A daily push happens even if Obsidian never opens (Priority: P4)

Even on days the user never launches Obsidian, the vault is still committed and pushed once a
day, catching up automatically if the machine was off, so notes are never stranded only on the
local disk.

**Why this priority**: A safety backstop; valuable but lowest priority because US3 already covers
the common (Obsidian-open) case. Independent and additive.

**Independent Test**: Run the sync module with stubbed `systemctl --user`; assert a user-level
oneshot service and a daily, persistent timer are installed and enabled, and that the service
command commits, rebases-with-autostash, and pushes over the deploy key, logging to a state file.

**Acceptance Scenarios**:

1. **Given** the sync module runs, **When** it installs the backstop, **Then** a `systemd --user` oneshot service and a `daily` + `Persistent=true` timer are written and enabled.
2. **Given** the timer fires, **When** the service runs, **Then** it stages all changes, commits (tolerating "nothing to commit"), pulls `--rebase --autostash`, and pushes using the dedicated deploy key, appending to `~/.local/state/devboost/vault-sync.log`.
3. **Given** the units are already installed and enabled, **When** the module re-runs, **Then** it is idempotent (no duplicate units, no error).

---

### Edge Cases

- **Secrets not provisioned**: no bootstrap token / git identity → the sync module fails fast with a named error (mirrors the secrets module's contract); the `apps` GUI installs are unaffected.
- **Vault repository empty or not yet existing**: clone of an empty repo still yields a working `~/Vault`; the first commit-and-push initializes it. A genuinely missing remote is a clear failure, not a silent skip.
- **Deploy key already registered** on the repo (re-provision / second machine): registration is idempotent — an existing matching key is detected and not duplicated.
- **Obsidian config present with user vaults**: registering `~/Vault` augments rather than replaces the user's vault list; never clobber existing entries.
- **Neither Flatpak nor native Obsidian config dir exists yet** (app never launched): the module creates the Flatpak config path (the default install) so the vault opens on first launch; a native path is written only if that install is detected.
- **No graphical/user session at install time** (headless first-boot): `systemd --user` units are enabled to start on the next user session (lingering/enablement handled), not assumed already-running.
- **Offline at install**: vault clone / deploy-key registration require the network; behavior on failure is a clear, named error (not a corrupt half-state). Whether the overall run treats this as fatal or non-blocking is specified in Assumptions.

## Clarifications

### Session 2026-06-21 (self-resolved, registry/context7-verified)

Driven autonomously (standing directive: no clarification prompts). Each ambiguity resolved
with the most defensible default grounded in the design doc + constitution + current registry
facts; concrete IDs/versions verified for 2026-06-21.

- Q: Does the `apps` profile ship dbgate as a Flatpak? → A: **No.** dbgate is the persistent
  container from the `data` stack (Spec 7 `templates/data/compose.yaml`); DBeaver is an optional,
  non-default alternative. (Resolves the roadmap row's stale dbgate entry — design doc supersedes.) [FR-005]
- Q: Which Flathub app IDs (verified)? → A: **md.obsidian.Obsidian, com.usebruno.Bruno,
  com.bitwarden.desktop, org.flameshot.Flameshot, org.localsend.localsend_app, org.videolan.VLC** —
  all confirmed HTTP 200 on the Flathub appstream API on 2026-06-21. These IDs are the in-repo
  source of truth (Principle III). [FR-001, FR-018]
- Q: Vault repository identity? → A: default repo name **`notes-vault`** under the provisioned
  GitHub user, configurable via a `$DEVBOOST_VAULT_REPO` env/secret (analogous to
  `$DEVBOOST_DOTFILES_REPO`). [FR-009, Assumptions]
- Q: Deploy-key security posture? → A: a **dedicated, repo-scoped, passphrase-less** ed25519 key
  registered as a **write** deploy key (unattended sync; a leaked laptop exposes only the notes
  repo). gnome-keyring-unlocked is a documented alternative, not the default. [FR-006, FR-007, SC-005]
- Q: Obsidian Git plugin `data.json` keys — current? → A: context7-verified against
  `/vinzent03/obsidian-git`: `autoPullOnBoot`, `autoBackupAfterFileChange`,
  `autoSaveInterval` (commit-and-sync every N minutes; set **10**), `autoPullInterval`,
  `pullBeforePush: true`, `syncMethod: "rebase"` (valid ∈ merge|rebase|reset),
  `commitMessage`/`autoCommitMessage`/`commitDateFormat` — all current keys, no drift. [FR-013]
- Q: Behavior when the network is down at install? → A: vault clone / deploy-key registration
  fail with a clear, **named fatal error** for the `obsidian-sync` module (consistent with other
  network-dependent modules); the `apps` GUI installs are independent and unaffected. [Edge Cases, Assumptions]
- Q: Which Obsidian config gets the vault registration? → A: always seed the **Flatpak** config
  path (the default install); also write the **native** path only when a native install is
  detected — never clobber existing user vault entries. [FR-010]

## Requirements *(mandatory)*

### Functional Requirements

**`apps` profile (GUI applications)**

- **FR-001**: The system MUST define an `apps` profile that installs the curated GUI app set: Obsidian, Bruno, Bitwarden, Flameshot, LocalSend, and VLC.
- **FR-002**: Each application MUST be its own data module (one module per app), installed from the Flathub remote that the base profile already configures, and MUST NOT require any engine (`bin/`, `lib/*.sh`) change to add.
- **FR-003**: Each app module MUST be idempotent (skip when already installed) and verify-guarded (verify confirms the app is present).
- **FR-004**: Each app module MUST declare Fedora-only install data so that on a non-Fedora OS the engine reports it unsupported (no install attempted).
- **FR-005**: The system MUST NOT install dbgate as a desktop/Flatpak app; the database GUI is the persistent dbgate **container** delivered by the `data` stack. DBeaver MUST remain a documented optional, non-default alternative. The roadmap/spec MUST reflect this reconciliation.

**`obsidian-sync` — vault provisioning & auto-open (depends on secrets, base/git, obsidian)**

- **FR-006**: The system MUST generate a dedicated, repo-scoped SSH key `~/.ssh/notes_vault_ed25519` for the notes vault, passphrase-less (or keyring-unlocked) for unattended use, generated only if absent.
- **FR-007**: The system MUST register that key as a **write** deploy key on the notes-vault repository via the GitHub API using the pre-provisioned bootstrap token, idempotently (no duplicate registration).
- **FR-008**: The system MUST write an isolated `~/.ssh/config` host alias that uses only the dedicated key (`IdentitiesOnly yes`) for the vault remote, leaving other SSH config untouched.
- **FR-009**: The system MUST clone the notes-vault repository to `~/Vault` over the isolated alias, idempotently (skip/refresh if already present).
- **FR-010**: The system MUST register `~/Vault` as an open-on-launch vault in Obsidian's configuration for the Flatpak install, and additionally for the native install when present, without clobbering existing user vault entries.
- **FR-011**: The system MUST export a `$VAULT_DIR` (= `~/Vault`) environment value via the managed shell configuration and register `~/Vault` as a recognized user directory.
- **FR-012**: The `obsidian-sync` module MUST require the `obsidian` app (and the secrets/git prerequisites) and MUST fail with a clear, named error when its prerequisites are absent (e.g., no bootstrap token, fresh editor/app missing).

**`obsidian-sync` — live sync & daily backstop**

- **FR-013**: The system MUST pre-seed the Obsidian Git plugin settings (`data.json`) with single-user multi-device defaults: auto-pull on boot, debounced commit-and-sync on file change, a periodic sync interval, pull-before-push, rebase sync method, and dated commit messages — **only if absent** (never overwrite committed/user settings).
- **FR-014**: The system MUST enable the Obsidian Git plugin in the vault's community-plugins listing (seed-if-absent).
- **FR-015**: The system MUST ensure vault `.gitignore` excludes local UI state (`.obsidian/workspace*.json`) and `.trash/`.
- **FR-016**: The system MUST install a `systemd --user` oneshot service and a `daily` + persistent (catch-up) timer that stages, commits (tolerating no-changes), pulls `--rebase --autostash`, and pushes the vault over the dedicated deploy key, logging to `~/.local/state/devboost/vault-sync.log`; both unit installation and enablement MUST be idempotent.

**Cross-cutting**

- **FR-017**: All install actions MUST be fully unattended (no prompts) and reproducible (curated app set; pinned plugin settings/version data are the in-repo source of truth where the source registry supports pinning).
- **FR-018**: All app IDs and the Obsidian Git plugin identity/settings MUST be verified against current registry/source data for the present date and recorded as in-repo data — not hardcoded from memory.
- **FR-019**: The work MUST keep the existing test suite green and extend the test harness in a backward-compatible way; tests MUST stub Flatpak, git, ssh/ssh-keygen, the GitHub API, and `systemctl --user` (no real network, Flatpak, or systemd).

### Key Entities *(include if feature involves data)*

- **App module**: one curated GUI application — its registry app ID, category (`apps`), profile membership (`apps`), Fedora install action, and verify predicate.
- **Notes vault**: the `~/Vault` working tree cloned from the notes-vault repository; carries its own committed `.obsidian/` (plugins + settings) that travels with the repo.
- **Vault deploy key**: a repo-scoped SSH keypair, its GitHub deploy-key registration (write), and its isolated SSH host alias.
- **Vault sync units**: the user-level oneshot service + daily persistent timer and their commit/pull/push command and log file.
- **Obsidian configuration**: the Flatpak and native config files that record which vault(s) open on launch.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After an unattended `apps` install on a clean machine, 6/6 curated apps are present and verify green, with zero prompts and zero app-store interactions.
- **SC-002**: Re-running the full feature is a complete no-op: 0 reinstalls, 0 duplicate deploy keys, 0 config rewrites, 0 duplicate systemd units.
- **SC-003**: After the sync run, Obsidian opens directly into `~/Vault` on first launch (vault registered in the active install's config) with no manual vault selection.
- **SC-004**: A notes change made while Obsidian is open is committed and pushed automatically without any manual git action; and on a day Obsidian is never opened, the daily timer still produces a push (catching up if the machine was off).
- **SC-005**: A lost/stolen laptop exposes no more than the single notes repository — the vault remote uses only the repo-scoped deploy key, never the account-wide key or a plaintext token.
- **SC-006**: The feature adds no engine changes (`bin/`, `lib/*.sh` engine logic untouched aside from feature-local data-layer helpers consistent with prior specs) and the full bats suite remains green.

## Assumptions

- **Base + secrets are present**: Flatpak + the Flathub remote are configured by the `base` profile; the bootstrap token, git identity, and `id_ed25519` are provisioned by the `secrets` profile (Spec 1). `obsidian-sync` depends on both.
- **Vault repository name/owner**: the notes vault repo is the design-doc `notes-vault` under the provisioned GitHub user; its name is configurable via the same environment/secret mechanism used elsewhere (e.g., a `$DEVBOOST_*` variable), defaulting to `notes-vault`.
- **Deploy-key security model**: the dedicated key is passphrase-less for unattended sync (acceptable because it is repo-scoped and write-only to a single notes repo); a gnome-keyring-unlocked variant is a documented alternative, not the default.
- **dbgate reconciliation (default applied)**: per the design doc, dbgate is the `data`-stack container, so the `apps` profile ships **no** dbgate Flatpak; DBeaver is optional/non-default. (Resolves the roadmap row's stale dbgate entry.)
- **Offline behavior**: vault clone / deploy-key registration are treated as a named, fatal error for the `obsidian-sync` module when the network is unavailable (consistent with other network-dependent modules); the `apps` GUI installs and the rest of the run are independent.
- **systemd --user enablement**: timers are enabled to run in the user session; where no session is active at install time, lingering/enablement is arranged so the timer activates on next login (no assumption of a live session during a headless first boot).
- **Obsidian default install is Flatpak**: the Flatpak config path is always seeded; the native config path is touched only when a native install is detected.
- **Plugin settings are pre-seeded, not owned**: because the vault's `.obsidian/` is committed and travels with the repo, dev-boost only seeds plugin settings when absent and never overwrites user-committed settings.
