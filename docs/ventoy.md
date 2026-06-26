# Ventoy USB & Kickstart (design §9)

Three layers: **Ventoy** = delivery (multi-ISO boot + auto-install + injection) · **Kickstart** =
unattended OS install + the BTRFS layout · **the `devboost` binary** = everything above the OS.

## Build the USB (once)
```sh
sudo devboost usb                  # interactive wizard: pick the device + ISO + profiles (defaults everywhere)
sudo devboost usb --device /dev/sdX --iso fedora-44 --secrets ./secrets.age --yes   # fully scripted
```
The `devboost usb` command (the typed replacement for the old `ventoy/make-usb.sh`) installs Ventoy on
the chosen **removable** disk, downloads + SHA256-verifies + caches the Fedora ISO, and stages the
injection archive (`devboost-<arch>.tar.gz`, which lands the binary at `opt/dev-boost/devboost`) +
`ks.cfg` + `ventoy.json`. The device picker lists removable disks with vendor/size/serial and requires
an explicit wipe confirmation (`--yes` to skip in automation). Optional wizard steps add extra
multi-boot ISOs/installers and an offline dnf+flatpak package mirror. Drop your `secrets.age` into
`Bootstrap/` (never committed). `ventoy/ventoy.json` binds `ks.cfg` to the Fedora ISO (`auto_install`)
and injects dev-boost (`injection`).

## Two boot paths
1. **Manual (primary):** boot Fedora ISO → installer → reboot → run `devboost install full`.
2. **Zero-touch (Kickstart):** auto-install entry → `ks.cfg` installs Fedora with the §10c BTRFS
   subvolume layout (root, home, mandatory `var/lib/gdm`, non-snapshot high-churn subvols, `/boot` in
   root, **no swap / zram-only**, `compress=zstd:1`) → `devboost-firstboot.service` runs
   `devboost install full` once (the injected binary at `/opt/dev-boost/devboost`), then disables itself.

## Safety
`devboost usb` only accepts a whole, removable, unmounted disk (`lsblk` guards) and requires an
explicit wipe confirmation before installing Ventoy — the single destructive step.

## Test it first (no hardware)
Validate both boot paths in a throwaway VM before touching a real stick — see
[vm-testing.md](vm-testing.md): `scripts/vm-test.sh usb --device /dev/sdX` (boot the real USB) or
`scripts/vm-test.sh usb --kickstart <netinst.iso>` (device-less zero-touch). Build the encrypted
secrets bundle with `scripts/make-secrets.sh`.
