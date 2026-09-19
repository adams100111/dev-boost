# pass across devices

`pass` is the credential store on every workstation (it ships in `base`). One private GitHub
repo — `adams100111/password-store` by default — is shared by all devices. Each device has
**its own GPG key**, credentials added anywhere reach every other device automatically, and
adding or removing a device is one explicit command.

`devboost pass` itself is **Linux-only until P2**: run it on macOS and it exits
`` `devboost pass` is Linux-only ``. macOS workstations get their own key and clone via P2's
launchd scheduling; until then modules that read secrets from `pass` just warn and skip there.

## Model

- **Per-device keys.** Each device generates an ed25519 key (`cv25519` encryption subkey,
  no expiry) whose uid is tagged `(devboost:<device>)`. The private key never leaves it.
- **Root `.gpg-id`** lists every workstation key, so every entry is encrypted to all of them.
  Access and trust are decided by **fingerprint (or long key id) only** — an email address in
  `.gpg-id` never grants access, because any key can carry any uid.
- **`.devboost/`** in the store holds only public keys and metadata:
  `devices/`, `pending/`, `revoked/` (`<name>.json` + `<name>.asc`) and `rotation.json`.
- **Passphrase:** asked by pinentry, then cached by gpg-agent for 8 h idle / 24 h max
  (`~/.gnupg/gpg-agent.conf`, set by the `pass` module).

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
- `devboost-pass-sync.timer` (systemd user timer) pulls with `--rebase --autostash`
  every 15 minutes, pushes anything unpushed (including a store whose very first push
  never landed), imports newly enrolled device keys (never a revoked one), deletes the
  public keys of revoked devices from this keyring, and notifies once per pending
  request. It also notifies once for every device key it finds listed that this device
  never saw before and did not approve itself (the tripwire — see
  [Trust root](#trust-root-what-revoke-guarantees)). State lives in
  `$XDG_STATE_HOME/devboost/pass-sync.json` (`notified`: already-announced requests;
  `known_devices`: device keys already seen — learnt silently on the first sync).
- Failures are logged to `~/.local/state/devboost/pass-sync.log` and notified; they never
  block anything else. A conflict in `.gpg-id` aborts the rebase — run
  `devboost pass sync --resolve` for the exact recovery steps. `--resolve` only **prints**
  guidance; it never touches the store itself.

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

## If every device is lost

The store is only as recoverable as one private key. Keep an **offline backup of one
device key** (`gpg --export-secret-keys --armor <fingerprint>` to an encrypted USB or
paper). Restore it on a new machine with `gpg --import`, run `devboost install` — it is
adopted — then revoke the lost devices.
