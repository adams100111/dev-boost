# Contract: `modules/secrets`

## `module.toml`
```toml
name        = "secrets"
category    = "base"
description = "Decrypt provisioned secrets; configure git identity + HTTPS credentials"
requires    = []
profiles    = ["base"]
verify      = "git config --global user.email >/dev/null 2>&1 && [ -f \"$HOME/.git-credentials\" ] && grep -q '@github\\.com$' \"$HOME/.git-credentials\""

[install]
default = "bash \"$DEVBOOST_ROOT/modules/secrets/install.sh\""

[install.fedora]   # only the age guarantee differs per OS; logic is in install.sh
# (install.sh calls ensure_pkg age "<per-os cmd>"; default arm covers all)
```
> `verify` is a top-level key evaluated BEFORE `[install]` (engine convention).

## `install.sh` behavior
Sources `lib/log.sh` + `lib/secrets.sh`. Steps (each idempotent):
1. `ensure_pkg age` with per-OS install (`fedora: sudo dnf install -y age`,
   `debian: sudo apt-get install -y age`, `macos: brew install age`); fail naming `age`
   if it cannot be made available.
2. `json="$(secrets_decrypt)"` — on missing/cannot-decrypt/incomplete, `die` with the
   exact reason (propagates as module install failure → engine reports module + cmd).
3. Extract `GIT_USER/GIT_EMAIL/GITHUB_PAT` (fail naming any missing field, FR-003).
4. `git config --global user.name/user.email`; `git config --global credential.helper store`.
5. Write `~/.git-credentials` line `https://<user>:<PAT>@github.com`, `chmod 600`.
   Replace any existing github.com line rather than appending a duplicate.
6. Never echo the PAT.

## Acceptance (maps to spec)
- US1-S1/S2: default + `--secrets PATH` (via `DEVBOOST_SECRETS`) both work, no prompt.
- US1-S3: re-run → `verify` green → engine skips (idempotent).
- US1-S4: after run, a private HTTPS clone authenticates from `~/.git-credentials`.
- US3-S3: tracked files contain no secret; credentials file is `600`.
