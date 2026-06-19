# Contract: `lib/secrets.sh` (sourced)

Source-only library (no side effects on source), mirroring `lib/*.sh` conventions.
Depends on `lib/log.sh` (for `die`/`log_*`), `jq`, `age`.

## Environment (all overridable; tests set them)
- `DEVBOOST_SECRETS` — explicit bundle path (also set from CLI `--secrets PATH`).
- `DEVBOOST_SECRETS_KEY` — age identity key file path.
- `DEVBOOST_BOOTSTRAP_DIR` — default search dir (default: first existing of the USB
  bootstrap mount, else `$DEVBOOST_ROOT`). Bundle default `$DEVBOOST_BOOTSTRAP_DIR/secrets.age`;
  key default `$DEVBOOST_BOOTSTRAP_DIR/age-key.txt`.

## Functions

### `secrets_bundle_path` → stdout: resolved bundle path; exit 0 if found, 1 if missing
Precedence `DEVBOOST_SECRETS` → default. Does not decrypt.

### `secrets_decrypt` → stdout: decrypted JSON; exit 0 ok
- Locates bundle + key; runs `age -d -i "$key" "$bundle"`.
- Missing bundle → exit 2, message "secrets bundle not found: <path>".
- Decrypt failure (bad/missing key) → exit 3, message "cannot decrypt secrets bundle".
- Output is JSON text (validated parseable by `jq -e .`); on invalid JSON → exit 4.
- MUST NOT write plaintext to any file.

### `secrets_get <KEY>` → stdout: value; exit 0 ok
- `secrets_decrypt | jq -r --arg k KEY '.[$k] // empty'`.
- Empty/missing required key → exit 5, message "secrets: missing required field <KEY>".

### `secrets_user` / `secrets_email` / `secrets_pat`
Convenience wrappers → `secrets_get GIT_USER|GIT_EMAIL|GITHUB_PAT`.

### `secrets_doctor` → exit 0 ready / non-zero with reason
- Prints one of: `ok`, `missing` (no bundle), `cannot-decrypt` (bundle present, decrypt
  fails), `incomplete` (decrypts but a required field is absent). Distinguishes the four
  states (FR-010). Used by `bin/devboost doctor`.

### `have <cmd>` / `ensure_pkg <pkg> <install-cmd>`
Minimal shared helpers (have = `command -v`). `ensure_pkg` runs the install cmd only if
`have` fails; used by modules to guarantee `age` etc.

## Guarantees
- No function prints the PAT to stdout/stderr in log lines.
- All failures name the operation (consistent with FR-014).
