# Validating dev-boost in a VM

Everything in dev-boost is unit-tested **hermetically** (all system calls stubbed). Before trusting it
on real hardware, validate it for real in a throwaway Fedora VM. Two paths, both supported by
`scripts/vm-test.sh`:

- **engine-only** — boot Fedora, install it, run `devboost install full`. Proves the *provisioning engine*. No USB, no root.
- **full USB** — boot the actual Ventoy USB (or drive `ventoy/ks.cfg` device-less). Proves the *delivery*
  layer (Ventoy → Kickstart → first-boot) too.

Start with **engine-only** — it's the fastest, safest signal.

## 0. Prerequisites (one time)

Fedora's native KVM stack (don't use VirtualBox — slower, conflicts with KVM):

```sh
grep -Eo 'vmx|svm' /proc/cpuinfo | head -1                 # non-empty ⇒ virtualization is on
sudo dnf install -y @virtualization virt-manager edk2-ovmf  # KVM + GUIs + UEFI firmware
sudo systemctl enable --now libvirtd
sudo usermod -aG libvirt "$USER"                            # then log out/in
```

`engine` and `usb --kickstart` run as your user (`qemu:///session`, no sudo). Booting a **physical USB**
(`usb --device`) needs `qemu:///system`, so that one path uses `sudo`.

## 1. Build the encrypted secrets bundle

`install.sh` provisions GitHub auth from an `age`-encrypted bundle (never committed):

```sh
scripts/make-secrets.sh --out /tmp/devboost-secrets
#   prompts for GitHub username, git email, and PAT (PAT is read silently, never logged)
#   → /tmp/devboost-secrets/secrets.age   (encrypted { GIT_USER, GIT_EMAIL, GITHUB_PAT })
#   → /tmp/devboost-secrets/age-key.txt   (the identity that decrypts it)
```
Both files are gitignored. Use them with `DEVBOOST_SECRETS=…/secrets.age devboost install full` (export
`DEVBOOST_SECRETS_KEY=…/age-key.txt`), or copy both to the USB `Bootstrap/` for zero-touch.
You can skip this and run profiles that don't need secrets (e.g. `cli,shell`) for a first smoke test.

## 2. Option A — engine-only (recommended first)

```sh
# Download a Fedora Workstation Live ISO from getfedora.org, then:
scripts/vm-test.sh engine --iso ~/Downloads/Fedora-Workstation-Live-x86_64-44.iso
```
This creates a UEFI VM (8 GiB / 4 vCPU / 50 GiB by default — override with `--ram/--vcpus/--disk`) and
boots the Live ISO. Then:

1. `scripts/vm-test.sh console` (or the auto-opened window) → click through the Fedora installer (~10 min) → reboot.
2. In the guest, get this repo (git clone, or copy it in) and run, **snapshotting between runs**:
   ```sh
   scripts/vm-test.sh snapshot clean      # (run on the HOST, right after first boot)
   # in the guest:
   devboost install cli shell       # fast smoke test
   devboost install full            # the whole workstation
   ```
3. Re-run from a pristine state any time: `scripts/vm-test.sh revert clean`.

**What to confirm** (per the definition of done):
- builds out of the box: `dotnet --info`, `uv --version`, `php`/`ddev` (Laravel), `node`/`pnpm` (web),
  Android SDK + `npx expo` (React Native);
- `devboost verify --profile full` is green; re-running `install` is a no-op;
- editors (`code`, `fresh`) + GUI apps present; Obsidian opens `~/Vault` and round-trips to GitHub;
- a "Fedora snapshots" entry appears in GRUB; `devboost doctor --gpu` reports sensibly.

## 3. Option B — full USB

### B1. Boot the real Ventoy USB (most faithful)
Build the USB first (see [ventoy.md](ventoy.md): `sudo "$(command -v devboost)" installer --device /dev/sdX --iso fedora-44 --secrets ./secrets.age --yes`,
`secrets.age`, `devboost.tar.gz`). Find the device with `lsblk -o NAME,SIZE,TYPE,RM,MOUNTPOINT,MODEL`,
then:
```sh
scripts/vm-test.sh usb --device /dev/sdX      # boots the USB via passthrough (sudo; qemu:///system)
```
The VM boots the Ventoy menu exactly like real hardware → pick Fedora (manual) **or** the auto-install
entry (zero-touch). Installs onto the VM's own virtio disk.

### B2. Device-less zero-touch (no physical USB)
Drives `ventoy/ks.cfg` directly to validate the Kickstart layout + first-boot service. Needs a Fedora
**netinst** or **Everything** ISO (the *Live* ISO does **not** support Kickstart `%packages`):
```sh
scripts/vm-test.sh usb --kickstart ~/Downloads/Fedora-Everything-netinst-x86_64-44.iso
scripts/vm-test.sh console        # watch the unattended install
```
The VM uses a SATA disk so the guest sees `/dev/sda`, matching `ks.cfg`'s `--only-use=sda`. After the
unattended install + reboot, `devboost-firstboot.service` runs `install.sh --profile full` once.

## 4. Lifecycle helpers

```sh
scripts/vm-test.sh list                 # all dev-boost test VMs
scripts/vm-test.sh snapshot <name>      # snapshot current state
scripts/vm-test.sh revert  <name>       # roll back (re-test from clean)
scripts/vm-test.sh console              # open the graphical console (virt-viewer)
scripts/vm-test.sh destroy              # stop + undefine + delete its disk
```
`--name` lets you run several VMs side by side; `--recreate` replaces an existing one.

## Caveats (this is first-real-run territory)
- The artifacts are fully unit-tested but **have never run on real hardware** — expect to fix a rough
  edge or two (e.g. the Kickstart `%post` copying the injected `dev-boost/` + `secrets.age` to
  `/opt/dev-boost`, or `--only-use=sda` vs `vda`). The **engine-only** path avoids these and is the
  cleanest first proof.
- `ks.cfg` targets `sda`; B2 forces a SATA disk to match. On real hardware with NVMe the disk is
  `nvme0n1` — adjust `ignoredisk --only-use=` accordingly.
- Give the VM ≥ 8 GiB RAM and ≥ 50 GiB disk for `--profile full` (the stacks + `system` pull a lot).
