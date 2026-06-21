# Recovery runbook

## Rebuild a machine
Boot the Ventoy USB → Fedora (manual or zero-touch Kickstart) → `install.sh --profile full`. Dotfiles,
secrets, vault, GUI apps and desktop are all restored. See [ventoy.md](ventoy.md).

## Bad update → reboot, not rebuild
Reboot → GRUB **"Fedora snapshots"** → boot the pre-update snapshot (snapper auto-snapshots before/after
every dnf transaction; the `system` profile provisions this). `dnf-automatic-security` only auto-applies
security updates, with snapshots as the safety net.

## GPU broken after a kernel update
`devboost doctor --gpu` (modprobe/nouveau-blacklist/initramfs/signature/dmesg checks). The
`nvidia-resign.service` re-signs + CRC32-recompresses the akmod modules for each new kernel before the
display manager starts, so kernel updates don't silently break the GPU.

## Memory starvation (orphan Aspire AppHosts)
`devboost dev status` (shows duplicates) → `devboost dev gc` (removes only dead-PID session containers,
never persistent infra). The `aspire-gc` timer runs `dev gc` hourly.

## Disk / data
`restic-backup` (real backups — snapshots are not backups). Air-gapped installers under the USB
`Installers/`. See also the USB-side [ventoy/Docs/recovery-runbook.md](../ventoy/Docs/recovery-runbook.md).
