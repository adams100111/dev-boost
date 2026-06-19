# Phase 1 Data Model: secrets-and-auth

This feature has no database; its "data" is a small set of files, their schema, and
permission/ownership rules. All paths are overridable in tests via env.

## Entities & artifacts

### 1. Encrypted secret bundle (`secrets.age`)
- **At rest**: age-encrypted ciphertext. Located by precedence:
  `--secrets PATH` → `$DEVBOOST_SECRETS` → default `<bootstrap>/secrets.age`.
- **Git**: MUST be gitignored (`*.age`). Never committed.
- **Decrypted form (in memory only)**: JSON object, e.g.
  ```json
  { "GIT_USER": "Jane Dev", "GIT_EMAIL": "jane@example.com", "GITHUB_PAT": "ghp_…" }
  ```
  - Required keys: `GIT_USER`, `GIT_EMAIL`, `GITHUB_PAT`. Extra keys ignored.
  - Parsed with `jq` (no shell sourcing).

### 2. Decryption identity key file
- age identity (private) key. Located by `$DEVBOOST_SECRETS_KEY` → default
  `<bootstrap>/age-key.txt` (or alongside the bundle).
- **Git**: gitignored; on disk MUST be mode `600`.

### 3. Git identity & credentials (written by `secrets` module)
- `~/.gitconfig`: `user.name = GIT_USER`, `user.email = GIT_EMAIL`,
  `credential.helper = store`.
- `~/.git-credentials`: one line `https://<user>:<PAT>@github.com`. Mode `600`.

### 4. SSH keypair (written/ensured by `ssh-setup` module)
- `~/.ssh/id_ed25519` (mode `600`), `~/.ssh/id_ed25519.pub` (mode `644`).
- Generated with no passphrase, comment `devboost:<hostname>`, only if absent.
- `~/.ssh/config`: hardened block referencing the key (`IdentityFile`,
  `IdentitiesOnly yes`, `AddKeysToAgent yes`, `HashKnownHosts yes`). Idempotent —
  managed block delimited by markers, never duplicated.

### 5. Registered GitHub keys (remote state)
- **Account key**: title `devboost:<hostname>`, body = `id_ed25519.pub`. One per host.
- **Deploy key** (reusable helper, consumed later): per-repo, title + `read_only` flag.
- Idempotency: matched by title OR identical key body via a `GET` pre-check.

### 6. State marker
- `~/.local/state/devboost/ssh-key-registered`: empty marker file written once the
  account key is confirmed registered (or found pre-existing). Drives offline-safe
  `verify`.

## Validation rules (from FRs)

| Rule | Source |
|------|--------|
| Bundle missing → distinct "missing" report; present-but-undecryptable → distinct "cannot-decrypt" report | FR-010 |
| Any required JSON key absent → fail naming the field; no partial config | FR-003 |
| `~/.git-credentials` & private key mode `600` (not group/other readable) | FR-012 |
| ed25519 key never overwritten if present | FR-005 |
| Account key not duplicated (title or body match) | FR-006 |
| Upload failure non-blocking unless `--strict` | FR-007 |
| No decrypted secret / token / private key tracked by git | FR-012 |

## Lifecycle / ordering

```
doctor (preflight: age present? bundle present & decryptable?)
  └─ secrets        (requires: none)  → git identity + credential store
       └─ ssh-setup (requires: secrets) → ed25519 + GitHub registration + ssh/config
```

`depsort` orders `secrets` before `ssh-setup` via `requires`. Both are reached through
the normal install loop; no special-casing.
