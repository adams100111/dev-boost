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

## Dry-run a rebuild (no hardware)
Rehearse the whole flow in a VM first: [vm-testing.md](vm-testing.md) —
`scripts/vm-test.sh engine --iso Fedora-Live.iso` (engine) or `scripts/vm-test.sh usb …` (full USB).

## Lost (or stolen) a laptop
1. **First, cut its GitHub access**: revoke its `gh auth` token / rotate the PAT and remove
   its SSH key in GitHub settings. Write access to the store repo is the trust root — while
   the laptop can still push, it could re-list its own key (see
   [pass.md](pass.md#trust-root-what-revoke-guarantees)).
2. On any other enrolled workstation: `devboost pass revoke <laptop>` — removes its key
   and re-encrypts the store. Its key can never be re-enrolled, under any name, and every
   device drops its public key on the next sync.
3. Rotate every entry it printed (change the secret at its source, then `pass edit
   <entry>`); `devboost doctor` lists what is left until all are done.
Lost **every** device? Restore your offline key backup — see [pass.md](pass.md#if-every-device-is-lost).
