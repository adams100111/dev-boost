# Contract: `modules/ssh-setup`

## `module.toml`
```toml
name        = "ssh-setup"
category    = "base"
description = "Generate ed25519 key and register it with GitHub (non-blocking)"
requires    = ["secrets"]
profiles    = ["base"]
verify      = "[ -f \"$HOME/.ssh/id_ed25519.pub\" ] && [ -f \"${XDG_STATE_HOME:-$HOME/.local/state}/devboost/ssh-key-registered\" ]"

[install]
default = "bash \"$DEVBOOST_ROOT/modules/ssh-setup/install.sh\""
```

## `install.sh` behavior
Sources `lib/log.sh` + `lib/secrets.sh` + `lib/github.sh`. Steps:
1. If `~/.ssh/id_ed25519` absent → `ssh-keygen -t ed25519 -N "" -C "devboost:$(hostname)"
   -f ~/.ssh/id_ed25519`. Never overwrite an existing key (FR-005). Ensure `~/.ssh` `700`,
   private key `600`.
2. Ensure a hardened, marker-delimited block in `~/.ssh/config` referencing the key
   (`IdentityFile ~/.ssh/id_ed25519`, `IdentitiesOnly yes`, `AddKeysToAgent yes`,
   `HashKnownHosts yes`). Idempotent (replace between markers, never duplicate).
3. `gh_upload_ssh_key ~/.ssh/id_ed25519.pub "devboost:$(hostname)"` using `secrets_pat`.
   - Success or already-registered → write state marker `…/devboost/ssh-key-registered`.
   - Failure → `log_warn` and **return 0 without writing the marker**.
   - Strict/non-strict is then handled by the **engine, unchanged**: after install it
     re-runs `verify`, which is red (no marker). `run_install` reports
     "verify failed after install" → aborts under `--strict`, continues otherwise
     (FR-007). On a later re-run, the red verify retries the upload (resumable). The
     module never needs to know the strict flag.
4. Never echo the PAT or private key.

## Acceptance (maps to spec)
- US2-S1: no key → ed25519 generated + uploaded once.
- US2-S2: key already registered (title/body) → no duplicate POST.
- US2-S3: upload network failure → warn + continue (default) / abort (strict).
- US2-S4: `~/.ssh/config` references ed25519 with hardened defaults; no prompt.
