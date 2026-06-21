# Ventoy USB & Kickstart (design §9)

Three layers: **Ventoy** = delivery (multi-ISO boot + auto-install + injection) · **Kickstart** =
unattended OS install + the BTRFS layout · **dev-boost `install.sh`** = everything above the OS.

## Build the USB (once)
```sh
sudo ventoy/make-usb.sh /dev/sdX            # DESTRUCTIVE: wipes the USB (refuses non-removable/system disks)
sudo ventoy/make-usb.sh /dev/sdX --update   # update Ventoy in place (no wipe)
```
Then copy ISOs into `ISO/`, and `secrets.age` + `devboost.tar.gz` into `Bootstrap/` (never committed).
`ventoy/ventoy.json` binds `ks.cfg` to the Fedora ISO (`auto_install`) and injects dev-boost (`injection`).

## Two boot paths
1. **Manual (primary):** boot Fedora ISO → installer → reboot → run `install.sh`.
2. **Zero-touch (Kickstart):** auto-install entry → `ks.cfg` installs Fedora with the §10c BTRFS
   subvolume layout (root, home, mandatory `var/lib/gdm`, non-snapshot high-churn subvols, `/boot` in
   root, **no swap / zram-only**, `compress=zstd:1`) → `devboost-firstboot.service` runs
   `install.sh --profile full` once, then disables itself.

## Safety
`make-usb.sh` only accepts a whole, removable, unmounted disk and requires explicit confirmation.

## Test it first (no hardware)
Validate both boot paths in a throwaway VM before touching a real stick — see
[vm-testing.md](vm-testing.md): `scripts/vm-test.sh usb --device /dev/sdX` (boot the real USB) or
`scripts/vm-test.sh usb --kickstart <netinst.iso>` (device-less zero-touch). Build the encrypted
secrets bundle with `scripts/make-secrets.sh`.
