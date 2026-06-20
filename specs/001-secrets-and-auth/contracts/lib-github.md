# Contract: `lib/github.sh` (sourced)

PAT-authenticated GitHub REST helpers. Depends on `lib/log.sh`, `curl`, `jq`.
Auth via `GITHUB_PAT` (arg or `secrets_pat`). All calls send:
`Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2022-11-28`.

## Environment (tests override)
- `GITHUB_API` — base URL (default `https://api.github.com`). Tests point at a stub.
- The `curl` binary is PATH-stubbed in tests.

## Functions

### `gh_api <METHOD> <path> [json-body]` → stdout: response body; exit: 0 if HTTP 2xx else 1
- Single point that runs curl with auth headers, captures body + status.
- Non-2xx → exit 1, `log_error` with the parsed `.message` (no PAT leaked).

### `gh_upload_ssh_key <pubkey-file> <title>` → exit 0
- `GET /user/keys`; if any key has `.title == <title>` OR `.key` equals the pubkey body
  → log "already registered", exit 0 (no POST). (FR-006 idempotency)
- Else `POST /user/keys` with `{title, key}`; 2xx → exit 0; failure → exit 1.

### `gh_add_deploy_key <owner> <repo> <pubkey-file> <title> [--read-only]` → exit 0
- `GET /repos/<owner>/<repo>/keys`; de-dupe by title or key body.
- Else `POST /repos/<owner>/<repo>/keys` with `{title, key, read_only}`.
- Reusable by the later `obsidian-sync` module (FR-013); default write (read_only=false)
  unless `--read-only`.

## Guarantees
- Idempotent: a second identical call performs no POST and exits 0.
- The PAT never appears in logs, error messages, or the curl-arg log used by tests
  (tests assert this).
