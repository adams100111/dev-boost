# Phase 0 Research: ventoy-kickstart-usb
Design §9/§10c oracle. Artifacts under ventoy/ (NOT engine; Principle I untouched). No new pinned tools.
## Decisions
- D0. Deliverables: ventoy/make-usb.sh, ventoy/ventoy.json, ventoy/ks.cfg, ventoy/devboost-firstboot.service,
  ventoy/Docs/recovery-runbook.md. Repo ships scripts/config only — ISOs/secrets.age/binaries off-repo.
- D1. make-usb.sh safety: resolve target via lsblk -dno NAME,TYPE,RM,MOUNTPOINT; accept ONLY type=disk,
  RM=1 (removable), not mounted, not a partition/loop; require `--yes` or interactive y/N confirm; then
  `ventoy -i <dev>` (or `-u` for --update); then lay out USB tree + copy ventoy.json/ks.cfg.
- D2. ventoy.json: control [VTOY_MENU_TIMEOUT=10, VTOY_DEFAULT_IMAGE=/ISO/Fedora-44.iso], auto_install
  [{image:/ISO/Fedora-44.iso, template:/Bootstrap/ks.cfg}], injection [{image:/ISO/Fedora-44.iso,
  archive:/Bootstrap/devboost.tar.gz}].
- D3. ks.cfg: text/format kickstart — part btrfs.* subvols per §10c with --label, compress=zstd:1 fsoptions,
  mandatory var/lib/gdm + non-snapshot subvols; reqpart/EFI; `# no swap` (zram via zram-generator default);
  %packages @^workstation-product-environment + git python3 jq -@swap; %post --log writes
  devboost-firstboot.service + systemctl enable.
- D4. devboost-firstboot.service: [Service] Type=oneshot, ExecStart=/bin/bash -lc 'devboost ... ||true;
  log; systemctl disable devboost-firstboot.service', After=network-online.target, WantedBy=multi-user.target.
## Testing
bats tests/ventoy.bats: stub lsblk (STUB_LSBLK knobs: device type/RM/mount) + ventoy (log); assert
make-usb.sh refuses non-removable/partition/loop/system + only runs ventoy -i on confirmed removable;
assert ventoy.json valid JSON (jq) + bindings; assert ks.cfg has all §10c subvols + compress=zstd:1 +
var/lib/gdm + no swap + firstboot %post; assert devboost-firstboot.service self-disables. Hermetic.
## Outcome: no unknowns; ready for Phase 1.
