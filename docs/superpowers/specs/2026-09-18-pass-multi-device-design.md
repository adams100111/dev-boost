# pass multi-device — design

**Date:** 2026-09-18 · **Status:** approved (grilling) · **Depends on:**
[macOS support](2026-09-18-macos-support-design.md) M1 (engine: `launchd`, `NeedsUser`,
keychain) for its macOS parts; Linux parts can land independently.

## Goal

`pass` is the credential store on every workstation. One GitHub repo
(`adams100111/password-store`, private) is shared by all devices; credentials added on
one device reach the others **automatically**, each device holds **its own GPG key**, and
adding or revoking a device is one explicit command.

## Current state (facts)

- The store is already encrypted to **two** GPG keys (commit 2026-09-03 "Reencrypt
  password store using new GPG id 01BD…994F, 64F4…6F56") — i.e. per-device keys.
- `pass` / `pass-store` live in the opt-in `security-cli` profile, yet `claude-*`,
  `codex-config` and (new) `herdr-plugins` read secrets from `pass`.
- `pass-store` clones `DEVBOOST_PASS_REPO` or runs `pass init $DEVBOOST_PASS_GPG_ID`;
  nothing generates or imports a device key, and nothing syncs.

## Decisions

| Topic | Decision |
|---|---|
| Default | `pass` + `pass-store` move into `base` (every OS) |
| Repo | Default `pass_repo = "adams100111/password-store"` in `~/.config/devboost/config.toml`; cloned over HTTPS via `gh` auth; `DEVBOOST_PASS_REPO` overrides |
| Key model | **Per-device GPG keys** (matches the store); the age bundle does **not** carry a GPG key |
| Passphrase | Device keys have a passphrase; cached for the session — macOS: pinentry-mac → login keychain; Linux: gpg-agent `default-cache-ttl`/`max-cache-ttl` 8 h / 24 h |
| Enrollment | New device pushes a pending request; **one-command approval** on any enrolled device (never automatic) |
| Revocation | `devboost pass revoke <device>` + rotation checklist tracked by `doctor` |
| Sync | post-commit hook pushes immediately; background pull every 15 min |
| Servers | Not by default; opt-in **scoped** enrollment via per-folder `.gpg-id` |

## Store layout additions

```
password-store/
  .gpg-id                         # unchanged: all workstation fingerprints (pass semantics)
  <folder>/.gpg-id                # only where a scoped server is enrolled
  .devboost/devices/<name>.json   # {name, fingerprint, os, enrolled_at, scope: null|["harness", …]}
  .devboost/devices/<name>.asc    # public key (armored)
  .devboost/pending/<name>.json   # enrollment request: {name, fingerprint, os, requested_at, scope}
  .devboost/pending/<name>.asc
  .devboost/rotation.json         # entries needing rotation after a revoke
```

`.devboost/` holds only public material and metadata — never secrets.

## Flows

### Enroll (new device) — `pass-store` install on a device without access
1. Clone the store (gh HTTPS).
2. If no local secret key matches any fingerprint in `.gpg-id` / `devices/`:
   generate an ed25519 GPG key (`gpg --batch --quick-gen-key "<user> (devboost:<device>)"
   ed25519 cert,sign never` + cv25519 encryption subkey), passphrase via pinentry.
3. Write `pending/<name>.{json,asc}`, commit, push.
4. Notify: ntfy + native notification on other devices on their next sync (see Sync).
5. Report `blocked (NeedsUser)`: "approve this device from an enrolled device:
   `devboost pass approve <name>`". Other modules reading `pass` degrade gracefully
   (warn + skip) until approved.

`<name>` defaults to the short hostname; `--name` overrides; collisions refused.

### Approve — `devboost pass approve [<name>]` (enrolled device)
1. `git pull --rebase`; list pending requests; show name, OS, **full fingerprint**,
   requested time, scope; require typed confirmation (`y`).
2. `gpg --import pending/<name>.asc`; set ownertrust for that key.
3. Workstation: `pass init $(all workstation fingerprints)` (re-encrypts everything).
   Scoped server: `pass init -p <folder> $(workstation fps + server fp)` per folder.
4. Move `pending/<name>.*` → `devices/`, commit "devboost: enroll <name>", push.
5. The new device's pull timer fetches the re-encrypted store; next `devboost install`
   (or the timer) verifies it can decrypt and clears the blocked state.

### Revoke — `devboost pass revoke <name>`
1. Remove fingerprint from `.gpg-id` (and any folder `.gpg-id`), re-encrypt, move
   `devices/<name>.*` to `.devboost/revoked/`, commit, push.
2. Write `rotation.json`: every entry that existed while `<name>` was enrolled (from
   `git log` of that period), because **git history still holds ciphertexts the revoked
   key can decrypt**. Print the checklist.
3. `doctor` lists unrotated entries; `pass edit`/`insert` of an entry clears it.

### Adopt existing devices
First run of the new `pass-store` on a device whose secret key already matches a
fingerprint in `.gpg-id` registers `devices/<name>.{json,asc}` automatically (no approval
— it already has access). This labels the two current keys.

### Sync
- `pass-store` installs a **post-commit hook** in the store's local `.git/hooks/`:
  `git push --quiet` in the background; failures logged.
- Background pull: every 15 min `git -C $PASSWORD_STORE_DIR pull --rebase --autostash`
  then push any unpushed commits. macOS: `launchd.user_agent("dev.devboost.pass-sync")`;
  Linux: systemd user timer `devboost-pass-sync.timer`.
- On pull, if new `pending/*` exist and this device is enrolled → notify once per request
  (ntfy + native/`notify` hook).
- Conflicts: entries are separate files; `.gpg-id` conflicts abort the rebase and notify
  (`devboost pass sync --resolve` guides a manual fix).

## Modules & CLI

- `pass` module: macOS brew `pass`, `gnupg`, `pinentry-mac` + `gpg-agent.conf`
  `pinentry-program`; Linux unchanged + gpg-agent cache TTLs.
- `pass-store` module: clone/enroll/adopt, hook, sync timer; verify = store present +
  (decryptable **or** pending request exists → `blocked`).
- `devboost pass` sub-app: `status`, `devices`, `approve [name] [--scope f…]`,
  `revoke <name>`, `sync [--resolve]`, `enroll [--name] [--scope f…]` (manual re-run).
- `herdr-plugins`: Telegram token from `pass show devboost/herdr-telegram`
  (`token`/`chat_id` lines), fallback env, else skip.

## Error handling

- Not approved yet → `NeedsUser` with the exact approve command; dependent modules warn
  and skip their pass reads (never fail the run).
- gh not authenticated → `NeedsUser` ("`gh auth login`").
- Push/pull failures → logged + notified; never block other modules.
- Approve refuses when the pending fingerprint's key file doesn't match its JSON.

## Testing

`FakeExecutor` + a temp git repo fixture with real `gpg` in an isolated `GNUPGHOME`
(skipped if gpg absent): enroll writes pending files; approve re-encrypts to N+1 keys and
the new key decrypts; scoped approve limits folders; revoke removes access for new
entries and builds `rotation.json` from history; adopt registers without approval; sync
hook/timer content per OS; pending-notification de-dup.

## Documentation

`docs/pass.md` (model, enroll→approve→sync, revoke + rotation, scoped servers, recovery
if all devices are lost: an offline backup of one device key is recommended),
`docs/credentials.md` (division: gh for GitHub, pass for everything else, age for
bootstrap), `docs/recovery-runbook.md` ("lost a laptop" → revoke + rotate), README.

## Rollout

| # | PR | Notes |
|---|---|---|
| P1 | Linux: profile move, default repo config, adopt + enroll + approve + revoke, sync timer + hook, `devboost pass` CLI, docs | lands independently — plan: [2026-09-19-pass-p1-linux](../plans/2026-09-19-pass-p1-linux.md) |
| P2 | macOS: pinentry-mac, launchd sync agent, native notifications | after macOS M1 — plan: [2026-09-19-pass-p2-macos](../plans/2026-09-19-pass-p2-macos.md) |

### P1 notes

- **Trust root.** Write access to the store repo is the trust root: whoever can push can
  list a key in `.gpg-id` + `.devboost/devices/`, and devices import it on sync. Revoke
  guarantees the key is dropped from every `.gpg-id` with re-encryption, is refused on
  any future request / import (under any name), and is deleted from every keyring on its
  next sync, and that `doctor` tracks the entries to rotate. It does **not** protect
  entries read before (git history), nor stop a device that can still push — cut its
  GitHub access first (runbook step 1). A sync tripwire notifies once per device key a
  device never saw and did not approve itself. Planned hardening: a signed `.gpg-id`
  (`PASSWORD_STORE_SIGNING_KEY`).
- **Carried to P2:** a recipient audit of entries inserted offline after a revoke
  (`gpg --list-packets`), so an entry still encrypted to a revoked key is reported
  (done in P2: `devboost pass audit`).
