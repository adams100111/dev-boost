# dev-boost USB — build & recovery runbook

## Build the USB (once, any OS)
```sh
sudo ventoy/make-usb.sh /dev/sdX        # DESTRUCTIVE: wipes the USB (refuses non-removable/system disks)
sudo ventoy/make-usb.sh /dev/sdX --update   # update Ventoy in place (no wipe)
```
Then copy onto the USB (no re-flashing — Ventoy boots ISOs directly):
- `ISO/Fedora-44.iso` (+ Ubuntu/Win11/SystemRescue/GParted as desired)
- `Bootstrap/secrets.age` (age-encrypted PAT — provisioned out-of-band, NEVER committed)
- `Bootstrap/devboost.tar.gz` (repo copy for injection)

## Two boot paths (Ventoy menu)
1. **Manual (primary):** boot Fedora ISO → GNOME installer (~10 min) → reboot →
   `cd /run/media/$USER/VTOY/Bootstrap/dev-boost && ./install.sh` (or `curl … | bash`).
2. **Zero-touch (Kickstart):** pick the auto-install entry → Ventoy feeds `ks.cfg` → Fedora installs
   unattended with the §10c BTRFS layout → `devboost-firstboot.service` runs `install.sh --profile full`
   on first boot, then disables itself.

## Recovery
- **Bad update:** reboot → GRUB "Fedora snapshots" → boot the pre-update snapshot (snapper).
- **GPU broken after kernel update:** `devboost doctor --gpu`; the `nvidia-resign.service` normally
  re-signs modules automatically before the display manager.
- **Air-gapped:** offline rpms/AppImages live under `Installers/`.

## Safety
`make-usb.sh` refuses any target that is not a whole, removable, unmounted disk, and requires an
explicit `yes` (or `--yes`) before wiping. ISOs and `secrets.age` are never committed to the repo.
