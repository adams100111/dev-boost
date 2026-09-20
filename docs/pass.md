# pass across devices

`pass` is the credential store on every workstation (it ships in `base`). One private GitHub
repo — `adams100111/password-store` by default — is shared by all devices. Each device has
**its own GPG key**, credentials added anywhere reach every other device automatically, and
adding or removing a device is one explicit command.

The store works on **Linux and macOS**. On a Mac, `devboost install` (its `macos` profile
installs `pass` + `pass-store`, like `base` does on Linux) enrolls this device the same
way; only the passphrase prompt (pinentry-mac) and the sync scheduler (launchd, not
systemd) differ per OS — see [Model](#model) and [Sync](#sync) below.


Every dev-boost setting lives in one place: **[configuration](configuration.md)**.

## Where your store lives

dev-boost ships **no default repo**. It finds yours in this order:

1. `DEVBOOST_PASS_REPO` (owner/repo or a git URL)
2. `pass_repo` in `~/.config/devboost/config.toml`
3. the `origin` remote of an existing clone at `~/.password-store`

```toml
# ~/.config/devboost/config.toml
pass_repo = "<owner>/<repo>"
```

If none of those answer, `pass-store` reports **blocked** with both ways to set it. It
never guesses a repo: a pass store is personal, and a built-in fallback would make every
other install try to clone a store it cannot read.

### A store that is already there but is not a clone

`devboost pass adopt`:

1. moves `~/.password-store` to `~/.password-store.pre-devboost` — **moved, never deleted**
2. clones your repo into its place
3. reports entries only in the old copy, entries new from the repo, and how many match

Only entry **names** are compared. Nothing is decrypted, and two GPG files holding the
same secret never have the same bytes, so contents cannot be compared without your
passphrase. Anything listed as "only in the old copy" is still on disk in the backup.


## Model

- **Per-device keys.** Each device generates an ed25519 key (`cv25519` encryption subkey,
  no expiry) whose uid is tagged `(devboost:<device>)`. The private key never leaves it.
- **Root `.gpg-id`** lists every workstation key, so every entry is encrypted to all of them.
  Access and trust are decided by **fingerprint (or long key id) only** — an email address in
  `.gpg-id` never grants access, because any key can carry any uid.
- **`.devboost/`** in the store holds only public keys and metadata:
  `devices/`, `pending/`, `revoked/` (`<name>.json` + `<name>.asc`) and `rotation.json`.
- **Passphrase:** asked by pinentry, then cached by gpg-agent for 8 h idle / 24 h max
  (`~/.gnupg/gpg-agent.conf`, set by the `pass` module on every OS). On macOS, the `pass`
  module also installs Homebrew `pass`, `gnupg` and `pinentry-mac`, and sets
  `pinentry-program /opt/homebrew/bin/pinentry-mac` in `gpg-agent.conf` (`/usr/local` on
  Intel). pinentry-mac's dialog offers **Save in Keychain**, which keeps the passphrase in
  your login keychain across reboots — for an interactive terminal read. An unattended run
  never opens pinentry-mac at all, so it never consults the keychain (see
  [Unattended runs](#unattended-runs)). `pinentry-program` is a managed setting: a value set
  by hand is replaced back to pinentry-mac on the next `devboost install`.

Choose the repo in `~/.config/devboost/config.toml` (`DEVBOOST_PASS_REPO` overrides):

```toml
pass_repo = "you/password-store"   # owner/repo on GitHub, or any git URL
device_name = "work-laptop"        # optional; default is the short hostname
```

The clone uses the GitHub access `secrets` set up (gh or the provisioned token). With
neither, `pass-store` reports `blocked` and asks for `gh auth login`.

## Add a device: enroll → approve → sync

1. On the new device: `devboost install` (or `devboost pass enroll` in a terminal).
   It clones the store, generates the key (you choose the passphrase), and pushes a
   request under `.devboost/pending/`. `pass-store` shows `blocked` with the next step;
   modules that read secrets from pass skip them for now — nothing fails.
   Unattended runs never generate a key: they tell you to run `devboost pass enroll`.
2. On any enrolled workstation: `devboost pass approve <name>`. Check the **full
   fingerprint** against the new device's `devboost pass status`, then type `y`. The store
   is re-encrypted to the new key and pushed. (With `DEVBOOST_NTFY_URL` set, the request
   pings your phone; enrolled desktops also show a notification on their next sync.)
   Approve refuses a request whose device name is already used by another key — re-request
   under a different name. A batch approve (`devboost pass approve` with no name) skips any
   bad request with a warning instead of aborting the rest.
3. The new device's sync timer pulls within 15 minutes (or run `devboost pass sync`);
   the next `devboost install` finds access and finishes the secret-reading modules.

Devices that already hold a key listed in `.gpg-id` are **adopted** on their first run —
registered under `.devboost/devices/` with no approval, because they already have access.
An empty store is initialised by its first device.

## Sync

- A `post-commit` hook in the store pushes every commit (`pass insert`, `edit`, …)
  in the background. All of this store's own git operations (the hook, `pass init`, sync)
  run non-interactively — no credential prompts, no commit signing — so nothing blocks on
  a hidden pinentry or GPG signature.
- On **Linux**, `devboost-pass-sync.timer` (systemd user timer) does the pulling; on
  **macOS**, the launchd agent `dev.devboost.pass-sync`
  (`~/Library/LaunchAgents/dev.devboost.pass-sync.plist`) does, on the same 900-second
  (15-minute) interval. It has no `RunAtLoad`: it can be loaded mid-`devboost install`,
  and firing immediately would race the installer's own git calls; launchd still runs a
  missed interval once on wake.
- Either way it pulls with `--rebase --autostash`, pushes anything unpushed (including a
  store whose very first push never landed), imports newly enrolled device keys (never a
  revoked one), deletes the public keys of revoked devices from this keyring, and
  notifies once per pending request. It also notifies once for every device key it finds
  listed that this device never saw before and did not approve itself (the tripwire —
  see [Trust root](#trust-root-what-revoke-guarantees)). State lives in
  `$XDG_STATE_HOME/devboost/pass-sync.json` (`notified`: already-announced requests;
  `known_devices`: device keys already seen — learnt silently on the first sync).
- `pass-store` counts the scheduler installed only once it is actually live: the systemd
  timer enabled *and* active on Linux, the launchd agent loaded on macOS — not just that
  its unit/plist file is on disk and matches the current `devboost` binary path.
  Rewriting a systemd unit (any devboost timer, not just this one) runs
  `systemctl --user daemon-reload`, so the new schedule takes effect without a re-login.
- Notifications (pending requests, conflicts, the tripwire, the recipient audit) use
  `notify-send` on Linux and `osascript` (Notification Center) on macOS.
- Failures are logged to `~/.local/state/devboost/pass-sync.log` and notified; they never
  block anything else. A conflict in `.gpg-id` aborts the rebase — run
  `devboost pass sync --resolve` for the exact recovery steps. `--resolve` only **prints**
  guidance; it never touches the store itself.

## Unattended runs

Outside a terminal — the sync agent/timer, a module reading a secret during
`devboost install`, … — any read from `pass` adds `--pinentry-mode error` to gpg's
options. A cached passphrase (see [Model](#model)) still works; with none cached, gpg
fails immediately instead of opening a pinentry dialog nobody is there to answer. The
secret is then skipped (never a hard failure), with a hint to run
`pass show <entry> >/dev/null` once in a terminal — that warms the gpg-agent cache
without printing the secret.

On macOS, it's pinentry-mac that reads the login keychain; with `--pinentry-mode error`,
gpg-agent never launches pinentry-mac at all, so a passphrase saved only via its **Save in
Keychain** checkbox is never consulted by an unattended run — only gpg-agent's in-memory
cache (8 h idle / 24 h max) is. After a reboot, or once that cache expires, unattended
secret reads are skipped until you do one `pass show` in a terminal, keychain or not.

## Recipient audit

An entry can end up encrypted to the wrong keys without ever failing to decrypt: it was
inserted offline after a revoke, before that device pulled the new `.gpg-id`, or before
an approval had reached every workstation. The audit catches both — every entry not
encrypted to exactly the keys its governing `.gpg-id` names.

It reads only each entry's recipient packets (`gpg --list-only --list-packets`) — it
never decrypts and never opens pinentry. It's surfaced in four places: `devboost pass
audit` (prints every mismatch), `devboost doctor`'s `pass-recipients` check, `devboost
pass status` (a mismatch count), and a sync notification the first time a new entry is
flagged.

`devboost pass audit` exits **1** if any entry is flagged (0 otherwise), and prints, per
mismatched entry, the recipients it has that its `.gpg-id` doesn't (`extra`) and the
`.gpg-id` keys it isn't encrypted to (`missing`),
plus a fix line: `pass init [-p <folder>] <the .gpg-id keys>` (the folder and the entry
name are shell-quoted; `pass init` re-encrypts only the entries that differ). If any
current recipient is a **revoked** device's key — decided by key id and fingerprint,
never by its label, so a pushed store file can't relabel a revoked recipient back into
an ordinary one — the fix line also says `, then change the secret: pass edit <entry>`,
because that device could already read the old ciphertext. A key id two different
primary keys claim is shown as a bare key id rather than a name; revoked keys are
resolved first, so this can never hide that an id was revoked.

A folder whose `.gpg-id` names a key by email, or that can't be read or decoded, is
reported as **not checked** rather than flagged — the audit only trusts fingerprints.

`devboost doctor`'s `pass-recipients` check fails on any mismatch. If the audit itself
errors (a malformed store, a failing `gpg`), only `pass-recipients` fails — `pass` and
`pass-rotation` are unaffected. The sync only re-runs the audit when `HEAD` moved since
the last one, and only notifies when the flagged set gains entries — it never raises,
so a broken audit can never break sync. Entry names are sanitised (control and bidi
characters stripped) everywhere they're shown: the log, the terminal and notifications.

## Revoke a device + rotate

`devboost pass revoke <name>` (from another enrolled workstation) removes the key from
every `.gpg-id`, re-encrypts, moves the device to `.devboost/revoked/`, and writes
`rotation.json`. **Git history still holds old ciphertexts the revoked key can decrypt**,
so every entry it could ever read must be changed at its source and updated with
`pass edit <entry>` (or `pass insert -f`). `devboost doctor` fails its `pass-rotation`
check until each one is done.

Revoke refuses to run while any `.gpg-id` in the store still names a key by email instead
of fingerprint — such a token could still resolve to the revoked key and survive
re-encryption. Replace it with the key's fingerprint (`pass init [-p <folder>] <fpr>…`)
and retry.

A revoked key never comes back: approve refuses a request carrying a revoked
fingerprint under any name, enrolling refuses it too (enroll under a new name to get a
fresh key), and no device imports it again.

## Trust root: what revoke guarantees

**Write access to the store repo is the trust root.** `.gpg-id` and `.devboost/devices/`
are plain files in git: anyone who can push to the repo can list a key of their own, and
every device will then import it on sync and encrypt new entries to it. Approval with a
typed `y` protects the normal path; it cannot stop someone who pushes directly.

What `devboost pass revoke` **guarantees**:

- the key is removed from every `.gpg-id` and the store is re-encrypted without it, so
  entries written from now on are unreadable to it;
- it can never be re-enrolled or re-imported (under any name), and every device deletes
  its public key on the next sync;
- `devboost doctor` tracks every entry it could ever read until each is rotated.

What it does **not** guarantee:

- anything a device read before — git history keeps old ciphertexts its key can
  decrypt, so rotate every listed entry at its source;
- anything against a device (or person) that can still push to the repo — it could add a
  new key of its own. **Cut its GitHub access first** (revoke its token / rotate the PAT,
  remove its SSH key), then revoke.

The **tripwire** narrows the gap: every sync notifies (once) when a device key this
device never saw appears in the store, so an unexpected addition is noticed. The planned
hardening is a **signed `.gpg-id`** (`PASSWORD_STORE_SIGNING_KEY`), so that a pushed
`.gpg-id` not signed by an enrolled device is rejected.

## Servers (scoped access)

Servers are not enrolled by default. To give one access to a single folder:
`devboost pass enroll --scope harness` on the server, then
`devboost pass approve <server>` on a workstation (`--scope` there overrides). Only that
folder gets its own `.gpg-id` (workstations + the server); everything else stays
unreadable to it. A scope must name at least one store-relative folder — an empty or
invalid scope (absolute, `..`, or a reserved folder like `.devboost`) is refused.

## Commands

| Command | Does |
|---|---|
| `devboost pass status` | this device's state, key, pending requests, rotation backlog, last sync |
| `devboost pass devices` | enrolled devices and pending requests |
| `devboost pass enroll [--name N] [--scope F]…` | request access for this device |
| `devboost pass approve [NAME] [--scope F]…` | approve pending requests (typed `y`) |
| `devboost pass revoke NAME` | revoke a device and print the rotation checklist |
| `devboost pass sync [--resolve]` | sync now / print conflict-recovery guidance |
| `devboost pass audit` | print entries not matching their `.gpg-id` keys; exits 1 if any flagged |

## If every device is lost

The store is only as recoverable as one private key. Keep an **offline backup of one
device key** (`gpg --export-secret-keys --armor <fingerprint>` to an encrypted USB or
paper). Restore it on a new machine with `gpg --import`, run `devboost install` — it is
adopted — then revoke the lost devices.
