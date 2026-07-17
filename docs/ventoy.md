# Ventoy USB & Kickstart (design §9)

Three layers: **Ventoy** = delivery (multi-ISO boot + auto-install + injection) · **Kickstart** =
unattended OS install + the BTRFS layout · **the `devboost` binary** = everything above the OS.

## Build the USB (once)

**Online — no clone, no build.** Install the builder, plug in the USB, then build:
```sh
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- usb
sudo devboost installer --dry-run    # 1. rehearse — prints the plan, touches NOTHING
sudo devboost installer              # 2. wizard — pick the USB, confirm the wipe
```
`bash -s -- usb` downloads the `devboost` binary **and its injection archive** (so `installer` works with
no clone) and puts `devboost` on PATH — without configuring this machine. It also best-effort-links
`devboost` into a root-PATH dir (when sudo permits) so plain `sudo devboost installer` resolves; if it ever
reports *command not found*, run once: `sudo ln -sf ~/.local/share/devboost/bin/devboost /usr/local/bin/devboost`.

Fully scripted (e.g. with secrets):
```sh
sudo devboost installer --device /dev/sdX --secrets ./secrets.age --secrets-key ./age-key.txt --yes
```

`devboost installer` is **self-contained** — no prerequisites to install by hand. It:
- **auto-downloads Ventoy** (pinned + SHA256-verified) and installs it onto the chosen **removable** disk
  (it runs Ventoy's `Ventoy2Disk.sh`; you do not install Ventoy yourself);
- downloads + SHA256-verifies **both** Fedora ISOs (Workstation Live + Everything-netinst);
- **mounts** the Ventoy data partition, stages the injection archive (binary → `opt/dev-boost/devboost`) +
  `ks.cfg` + a generated `ventoy.json` + your secrets, then **unmounts + syncs**.

The device picker lists only removable disks (vendor/size/serial) and requires an explicit wipe
confirmation — `--yes` skips it in automation; `--rebuild` wipes an existing dev-boost stick (otherwise
re-running an existing dev-boost stick does a non-destructive **update**).

**Caching:** the **wizard keeps** what it downloads, in the directory its "Cache dir for downloads"
prompt asks about (default under `$TMPDIR`, so pick something durable like `~/.cache/devboost` if you
want it to survive a reboot). On the flags path, pass `--cache-dir <path>` to keep downloads for reuse,
optionally with `--cache-ttl-days N` to evict files older than N days; `--device` **without**
`--cache-dir` is ephemeral (temp dir, cleaned after the build).

**Already have the ISO?** Pass `--iso-path <file>` (or answer the wizard's "Local ISO" prompt) to use it
instead of downloading. It must be the ISO pinned in `catalog.toml` for the selected OS + arch: it is
verified against that pin *before* anything is wiped, and a mismatch stops the build naming both hashes.
The file is used where it lies — never copied into the cache. The netinst and Ventoy tarball still
download.

**Secrets:** `--secrets secrets.age --secrets-key age-key.txt` (build the bundle with
`scripts/make-secrets.sh`); both are staged into `Bootstrap/` and copied onto the installed system by the
Kickstart `%post`. The engine **generates** `ventoy.json`: default boot + `injection` cover the Live ISO,
`auto_install` binds `ks.cfg` to the **netinst** ISO (injection covers both, so the binary is present on
either boot path).

## Which OS gets installed (`catalog.toml`)

The selectable OSes live in **`catalog.toml`** at the repo root (bundled into the binary like
`profiles.toml`). For each supported OS and architecture, `devboost installer` stages **two ISOs**:

- **Workstation Live** — the standard desktop image (manual installer or live session; Ventoy default
  boot entry).
- **Everything netinst** — a minimal network-install image wired to `auto_install` + `ks.cfg` for the
  zero-touch Kickstart path (no user interaction; BTRFS layout + firstboot service).

Both are pinned per-arch in `catalog.toml` with real SHA256s from Fedora's signed `CHECKSUM`, and both
are SHA256-verified on download. `devboost installer` auto-detects the host architecture and resolves both ISOs
automatically — no flags required. Adding a release or distro is one TOML table — no code change, no
rebuild of the engine logic — and the file is validated on load (a bad/short sha256 fails loudly).

## Update vs rebuild

Re-running `devboost installer` on a stick that is **already a dev-boost USB** detects it (via the
`Bootstrap/.devboost-usb.json` marker, read through a read-only mount) and defaults to a
**non-destructive update**: it runs `ventoy -u`, re-stages the `devboost` binary, `ks.cfg`,
`ventoy.json`, and refreshes the marker — while **preserving** `ISO/`, `secrets.age`, and the data
partition. Pass `--refresh-iso` (or accept the wizard prompt) to also re-download the pinned Fedora
ISO. A blank disk or a foreign Ventoy stick still goes through the explicit wipe confirmation.

## Preview first (`--dry-run`)

`devboost installer --device /dev/sdX --dry-run` resolves everything — catalog OS, detected disk state,
build-vs-update mode, profiles, and the ISO source — and prints the plan **without running `ventoy`,
downloading, or writing anything**. Use it to rehearse safely.

## Two boot paths

The Ventoy menu lists **both** ISOs. They behave completely differently, and the one that
provisions is *not* the default — pick deliberately:

| Menu entry | What it does to the target's disk | Do you get dev-boost? |
|---|---|---|
| `fedora-44.iso` (Workstation Live) — **the menu default**, auto-boots after `VTOY_MENU_TIMEOUT` (10s) | Nothing until you tell Anaconda to. You choose the disk, partitioning, dual-boot, shrink. | **No.** |
| `fedora-44-netinst.iso` → *Boot in normal mode* → **`/Bootstrap/ks.cfg`** | **Erases the entire first internal disk. No prompt, no confirmation, then reboots.** | Yes — fully. |

1. **Manual (Live ISO).** The stock Fedora installer: full control over disks and partitions.
   You get plain Fedora, because `ks.cfg`'s `%post` is what copies the injected binary to the
   target and enables the firstboot service — and `%post` only runs on the Kickstart path.
   Provision afterwards with the online installer (`get.sh`), or `devboost install full`.
2. **Zero-touch (Kickstart).** `%pre` picks the target itself: the first **real**, non-removable
   disk that is not the boot media (virtual devices like zram/loop/dm are skipped — `/dev/zram0`
   is `TYPE=disk RM=0` and `lsblk` cannot tell it from an internal disk; if nothing qualifies it
   refuses rather than guessing). Then `clearpart --all` and the §10c BTRFS subvolume layout
   (root, home, mandatory `var/lib/gdm`, non-snapshot high-churn subvols, `/boot` in root,
   **no swap / zram-only**, `compress=zstd:1`) → `devboost-firstboot.service` runs
   `devboost install full` once (the injected binary at `/opt/dev-boost/devboost`), then
   disables itself.

**There is no middle option**: no disk picker, no "install alongside", no dual-boot on the
zero-touch path — that is what "zero-touch" costs. Automation *or* partition control, not both.
Boot the netinst only on a machine whose disk is expendable. With **two or more** internal disks
`%pre` refuses rather than guess (enumeration order is not stable) — name the target explicitly by
adding a **`devboost.disk=<name>`** kernel argument to the boot entry (e.g. `devboost.disk=nvme0n1`;
edit the entry in the Ventoy menu with `e`). On a single-disk box it is auto-detected and the arg is
optional, but if given it must match.

Ventoy's own **"Check the file checksum"** entry (SHA-256) verifies an ISO against the
`catalog.toml` pin before you commit — worth the two minutes, since a truncated ISO fails
*after* the disk is already gone.

## Safety
Two different disks are at risk, at two different times:

- **The USB, at build time.** `devboost installer` only accepts a whole, removable, unmounted
  disk (`lsblk` guards), and requires an explicit wipe confirmation before installing Ventoy.
  Mounted partitions on the target are unmounted only *after* you confirm.
- **The target's internal disk, at boot time.** The zero-touch entry erases it with **no
  confirmation at all** — the kickstart runs unattended by design (`text`, `reboot`,
  `rootpw --lock`). The build-time confirmation protects the stick, not the laptop.

## Test it first (no hardware)
Validate both boot paths in a throwaway VM before touching a real stick — see
[vm-testing.md](vm-testing.md): `scripts/vm-test.sh usb --device /dev/sdX` (boot the real USB) or
`scripts/vm-test.sh usb --kickstart <netinst.iso>` (device-less zero-touch). Build the encrypted
secrets bundle with `scripts/make-secrets.sh`.
