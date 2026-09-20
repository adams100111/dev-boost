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

dev-boost provisions GitHub auth from an `age`-encrypted bundle (never committed):

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
Build the USB first (see [ventoy.md](ventoy.md): `sudo devboost installer --device /dev/sdX --iso fedora-44 --secrets ./secrets.age --yes`,
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
`ks.cfg` auto-detects the target disk in `%pre` (sda/vda/nvme0n1), so it installs onto the VM's disk
without tweaking. After the unattended install + reboot, `devboost-firstboot.service` runs
`devboost install full` once.

## 4. Lifecycle helpers

```sh
scripts/vm-test.sh list                 # all dev-boost test VMs
scripts/vm-test.sh snapshot <name>      # snapshot current state
scripts/vm-test.sh revert  <name>       # roll back (re-test from clean)
scripts/vm-test.sh console              # open the graphical console (virt-viewer)
scripts/vm-test.sh destroy              # stop + undefine + delete its disk
```
`--name` lets you run several VMs side by side; `--recreate` replaces an existing one.

## 5. macOS (tart)

Rehearses the `curl | bash` install in a throwaway Apple Silicon VM, on the Mac itself —
`scripts/vm-test-macos.sh` (design §9.5). It drives the guest entirely through the Tart
Guest Agent (`tart exec`); there is no sshpass or key setup. `--dry-run`, as the first
flag, prints the exact `tart` argv instead of running it, so every example below is safe
to preview without `tart` installed.

**Install tart, then pull the base images:**
```sh
brew install cirruslabs/cli/tart
tart pull ghcr.io/cirruslabs/macos-golden-gate-base:latest   # macOS 27 (primary)
tart pull ghcr.io/cirruslabs/macos-tahoe-base:latest         # macOS 26 (supported)
```

**Every verb** (`--name` defaults to `devboost-mac<os>`; `create` requires `--os 27|26`,
the rest default to 27):
```sh
scripts/vm-test-macos.sh create --os 27                  # tart clone + set cpu/memory/disk
scripts/vm-test-macos.sh create --os 27 --recreate       # destroy the old one, then recreate
scripts/vm-test-macos.sh snapshot clean --os 27          # stop, then clone -> devboost-mac27--clean
scripts/vm-test-macos.sh revert clean --os 27            # stop, delete, restore the snapshot clone
scripts/vm-test-macos.sh list                            # tart list
scripts/vm-test-macos.sh shell --os 27                   # prints: ssh admin@$(tart ip devboost-mac27)  # password: admin
scripts/vm-test-macos.sh run --os 27                     # boot, curl|bash the real release, smoke-assert.sh
scripts/vm-test-macos.sh destroy --os 27                 # stop + tart delete
```
`run` boots the VM headless (`tart run --no-graphics`), waits on `tart ip --wait 120`, then
runs the public one-liner (`curl … get.sh | bash -s -- macos`) inside the guest via
`tart exec -i`. Only when that succeeds does it run `scripts/smoke-assert.sh cli` in a
**second** `tart exec`: a fresh `zsh -lc` login shell (the user's real macOS shell), so the
smoke sees the PATH the install wired up (`~/.local/bin`, Homebrew, mise) rather than the
PATH of the shell that ran `get.sh`. It exits with the first failing command's exit code.

**`--local DIR` — rehearse an unpublished build before tagging (D9):**
```sh
bash scripts/build-bundle.sh                    # writes dist/devboost-darwin-arm64 + checksums-darwin-arm64.txt
scripts/vm-test-macos.sh run --local dist --os 27
```
Stages `get.sh`, `smoke-assert.sh` and `dist/`'s release files into a fresh `mktemp -d`
(never `dist/` itself), shares it into the guest at `/Volumes/My Shared Files/dist`
(`tart run --dir=dist:<path>`), and runs the staged file as
`DEVBOOST_RELEASE_BASE=file:///Volumes/My%20Shared%20Files/dist bash "/Volumes/My Shared
Files/dist/get.sh" macos` — the URL percent-encoded (curl rejects raw spaces), and the
profiles passed straight to the script file (`-s --` is only for `curl | bash`). No network
is needed inside the guest. `--local` refuses a directory without
`devboost-darwin-arm64`; `--dry-run` stages nothing. A raw `dist/` only carries `checksums-darwin-arm64.txt`; the staged copy is
renamed to `checksums.txt`, the name `get.sh` / `self-update` verify against.

**Credentials:** every tart macOS image logs in as **admin/admin** — `shell`'s hint
(`ssh admin@$(tart ip <vm>)`) is printed only, never dialled automatically.

**Screen Sharing is broken on the 27 image (V7).** `launchctl`-enabled Screen Sharing on
`macos-golden-gate-base` has no TCC rights (cirruslabs/macos-image-templates#376), so it
cannot drive or observe a GUI step. For a one-off GUI need, boot with graphics instead of
headless (`tart run <vm>`, not this script's always-headless `run` verb) rather than
reaching for VNC.

**The smoke verifies `cli`, not the install profiles.** An unattended guest has no
password, no TCC grants and no GitHub session, so every module that needs a human is
reported `blocked` by design and `devboost verify macos` can never exit 0 there. `cli`
is the largest set a guest with nobody at the keyboard can have fully green, so a real
regression still fails the smoke. Override with `--smoke-profiles "<profiles>"` when a
human is driving the guest.

**The only accepted non-green items in a macOS guest:**
- **No nested virtualization** — a Colima VM (what `docker` / `data-services` / `ddev`
  need) never starts inside a tart VM, so the Docker runtime fails to start. Expected, not
  a regression.
- **TCC grants need the GUI** — Full Disk Access, Screen Recording, and similar prompts
  need someone to click "Allow," which an unattended `tart exec` run cannot do. Expect
  those checks to fail here even though they'd pass on a real Mac with someone at the
  keyboard.

## 6. Linux smoke (CI)

`.github/workflows/vm-smoke.yml`'s `linux-smoke` job (M6, D6) is the CI-native alternative
to this doc's Fedora VM path, for a change that only needs to prove the shared shell files
plus a couple of Linux-only install sources — not a full `devboost install full`. It runs
`devboost install cli ghostty` then `scripts/smoke-assert.sh cli ghostty` (under `uv run`,
so the source-installed `devboost` is on PATH) as an unprivileged user on three legs — Fedora and Arch containers on the `ubuntu-24.04` runner
(there is no Fedora/Arch tart image, V9), plus the `ubuntu-24.04` runner host itself (real
systemd + snapd, which a container can't provide) — then confirms Ghostty came from its
real per-distro source: the `scottames/ghostty` COPR (Fedora), the snap (Ubuntu), pacman
(Arch). It runs `continue-on-error: true` (advisory) on `workflow_dispatch` and nightly,
same as `kickstart-smoke` above.

The **libvirt fallback** — actually booting Fedora/Ubuntu the way §§0–4 of this doc do —
stays the documented manual path for anything `linux-smoke`'s containers can't probe (a
real bootloader, a GNOME session, a full `devboost install full`): `scripts/vm-test.sh`
from a Linux host, as above.

## Caveats (this is first-real-run territory)
- The artifacts are unit-tested but **have not been booted on real hardware**. The Kickstart `%post`
  binary/secrets copy and the `%pre` disk auto-detect are implemented (2026-06-27 rebuild) but unproven
  on a real Anaconda install. The **engine-only** path avoids the delivery layer and is the cleanest
  first proof.
- `ks.cfg` auto-detects the target disk in `%pre` (sda/vda/nvme0n1) — no manual `--only-use=` tweak.
- Give the VM ≥ 8 GiB RAM and ≥ 50 GiB disk for `--profile full` (the stacks + `system` pull a lot).
