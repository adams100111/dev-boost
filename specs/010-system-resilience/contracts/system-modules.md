# Contract: system resilience/maintenance modules

Each: category="system", Fedora-only [install], idempotent, verify-guarded. Stubbed dnf/systemctl/grub.
- snapper: install + create root config if absent; verify config 'root' exists. Non-Btrfs → named fail.
- snapper-dnf-hook: install python3-dnf-plugin-snapper; verify rpm -q.
- grub-btrfs: install + enable grub-btrfsd + regen grub menu; verify enabled.
- btrfs-assistant / btrfsmaintenance / fwupd / power-profiles-daemon / thermald / smartmontools:
  dnf install + enable service/timer; verify enabled / rpm -q.
- dnf-automatic-security: install dnf-automatic; write /etc/dnf/automatic.conf upgrade_type=security
  (honor DEVBOOST_DNF_AUTOMATIC_CONF override for tests); enable dnf-automatic.timer; verify config has
  'upgrade_type = security' AND timer enabled. Tests: assert security-only (NOT default/full).
- restic-backup: install restic; seed sample repo conf + restic-backup.{service,timer} (no secrets);
  enable timer; verify units present.
- earlyoom: install; write /etc/default/earlyoom (honor override) with --avoid (dockerd|dotnet|dcp|sshd|
  code|gnome-shell) + --prefer (browsers/electron); enable; verify config has both patterns + enabled.
Tests (tests/system.bats): install attempted per module; verify GREEN; idempotent; unsupported-OS.
