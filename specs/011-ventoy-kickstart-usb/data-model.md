# Phase 1 Data Model: ventoy-kickstart-usb
Artifacts (no engine/profiles/module changes).
| artifact | shape |
|---|---|
| ventoy/make-usb.sh | bash; args <device> [--update] [--yes]; lsblk safety guard; ventoy -i/-u; USB tree layout |
| ventoy/ventoy.json | JSON: control(timeout/default) + auto_install(ks.cfg↔Fedora ISO) + injection(devboost.tar.gz) |
| ventoy/ks.cfg | Fedora kickstart: §10c btrfs subvols + ESP + compress=zstd:1 + no swap; minimal %packages; %post firstboot |
| ventoy/devboost-firstboot.service | systemd oneshot: install.sh --profile full --secrets; log; self-disable |
| ventoy/Docs/recovery-runbook.md | recovery + USB build docs |
## §10c subvolumes (ks.cfg)
snapshot-managed: root→/, home→/home. MANDATORY writable: var/lib/gdm. non-snapshot: opt, var/cache,
var/log, var/spool, var/tmp, var/lib/containers, var/lib/flatpak, var/lib/libvirt. /boot in root; ESP;
no swap (zram); compress=zstd:1 all btrfs.
## FR traceability: FR-001 make-usb tree · FR-002 safety guard · FR-003 ventoy.json · FR-004 ks.cfg btrfs ·
FR-005 %packages+%post · FR-006 firstboot service · FR-007 docs+hermetic tests.
