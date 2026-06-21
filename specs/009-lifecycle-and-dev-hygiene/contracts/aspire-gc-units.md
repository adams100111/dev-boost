# Contract: aspire-gc module (systemd --user hourly dev gc)  (FR-011)

aspire-gc module: category="dev-hygiene", requires=["docker"], profiles=["dev-hygiene"], Fedora-only [install].
## install.sh
- write ~/.config/systemd/user/aspire-gc.service (Type=oneshot, ExecStart `devboost dev gc`, log to
  ~/.local/state/devboost/aspire-gc.log) + aspire-gc.timer (OnCalendar=hourly, Persistent=true,
  WantedBy=timers.target); `systemctl --user enable --now aspire-gc.timer`; `loginctl enable-linger`. Idempotent.
## verify.sh
- both unit files present under ~/.config/systemd/user/.
## Tests (tests/aspire-gc.bats, stubbed)
- units written with OnCalendar=hourly + ExecStart dev gc; enable --now + enable-linger invoked;
  idempotent re-run; verify RED before / GREEN after; unsupported-OS → engine failure.
