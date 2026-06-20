# Contract: daily push backstop — systemd --user units (`obsidian-sync`, US4)

`vault_systemd_units` (FR-016) writes user units under `~/.config/systemd/user/` and enables them;
idempotent (overwrite-in-place + enable is a no-op when already enabled). Plus `loginctl enable-linger`
so the timer runs without an active session (headless first boot).

## Units
`devboost-vault-sync.service` (Type=oneshot):
```
ExecStart=/bin/bash -lc 'git -C "$HOME/Vault" add -A && \
  git -C "$HOME/Vault" commit -m "vault backup: $(date -Is)" --quiet || true; \
  git -C "$HOME/Vault" pull --rebase --autostash && git -C "$HOME/Vault" push'
```
- logs appended to `~/.local/state/devboost/vault-sync.log` (StandardOutput/Error=append: or the
  ExecStart redirects); uses the deploy key via the ssh alias remote.

`devboost-vault-sync.timer`:
```
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```
- enabled via `systemctl --user enable --now devboost-vault-sync.timer`.

## verify.sh (US4 portion)
- both unit files present under `~/.config/systemd/user/` AND the timer reported enabled
  (`systemctl --user is-enabled devboost-vault-sync.timer`).

## Tests (`tests/obsidian-sync.bats`, stubbed)
- assert both unit files written with the correct directives (OnCalendar=daily, Persistent=true,
  Type=oneshot, the add/commit/pull --rebase --autostash/push command, the log path).
- assert `systemctl --user enable --now devboost-vault-sync.timer` invoked (STUB_SYSTEMCTL_LOG) and
  `loginctl enable-linger` invoked; idempotent re-run (no duplicate units, enable is no-op).
- No real systemd: `systemctl --user`/`loginctl` are stubs that only log.
