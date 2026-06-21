# Contract: ventoy USB artifacts (hermetic tests)
## make-usb.sh (FR-001,002)
- args: <device> [--update] [--yes]. Resolve via `lsblk -dno NAME,TYPE,RM,MOUNTPOINT <dev>` (stub).
- REFUSE (exit!=0, no `ventoy` call): type!=disk (partition/loop), RM!=1 (non-removable), mounted (system),
  or device path not a whole block dev. Require --yes (or interactive y) before destructive.
- On confirmed removable: `ventoy -i <dev>` (or `-u` if --update); mkdir USB tree ISO/Bootstrap/Installers/
  Backups/ventoy; copy ventoy.json→USB/ventoy/, ks.cfg→USB/Bootstrap/.
- Tests: STUB_LSBLK_TYPE/RM/MOUNT knobs → refuse cases assert no `ventoy` in STUB_VENTOY_LOG; happy path
  (removable, --yes) asserts `ventoy -i` invoked.
## ventoy.json (FR-003): jq '.' valid; .auto_install[0].template == /Bootstrap/ks.cfg; .injection[0].archive
  == /Bootstrap/devboost.tar.gz; .control has VTOY_MENU_TIMEOUT + VTOY_DEFAULT_IMAGE.
## ks.cfg (FR-004,005): grep asserts — subvol root/home/var/lib/gdm + the 7 non-snapshot subvols;
  compress=zstd:1; no `^swap`/`part swap` (zram only); %packages has git+python3+jq; %post enables
  devboost-firstboot.service.
## devboost-firstboot.service (FR-006): Type=oneshot; ExecStart references install.sh --profile full +
  --secrets + /var/log/devboost-firstboot.log; self-disable (systemctl disable) present.
