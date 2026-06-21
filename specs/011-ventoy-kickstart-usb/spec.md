# Feature Specification: ventoy-kickstart-usb

**Feature Branch**: `011-ventoy-kickstart-usb`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "ventoy-kickstart-usb — the shippable USB: make-usb.sh, ventoy.json, ks.cfg (BTRFS layout), devboost-firstboot.service."

## User Scenarios & Testing *(mandatory)*

This feature is **the shippable artifact** — a Ventoy USB that boots Fedora and reaches a fully
configured workstation with two paths: manual (`curl … | bash`, primary) and zero-touch Kickstart
(bonus). Three clean layers (design §9): Ventoy = delivery, Kickstart = unattended OS install + the
§10c BTRFS layout, dev-boost `install.sh` = everything above the OS. These are USB build/config
artifacts under `ventoy/`, not engine modules; they are validated hermetically (no real USB/disk).

### User Story 1 - Build the USB safely (Priority: P1)

A maintainer runs `ventoy/make-usb.sh <device>` to install Ventoy onto a USB and lay out the directory
tree. The script refuses to touch a non-removable/system disk and confirms the target before any
destructive action, so the shippable medium is created without risking the workstation's own disk.

**Why this priority**: Without a safe builder there is no USB; the destructive-disk guard is the single
most important safety property.

**Independent Test**: With stubbed `lsblk`/`ventoy`, run `make-usb.sh` against (a) a non-removable disk
→ refuses, no `ventoy -i` invoked; (b) a removable device with confirmation → invokes `ventoy -i` and
creates the USB tree (ISO/Bootstrap/Installers/Backups/ventoy).

**Acceptance Scenarios**:

1. **Given** a target that is non-removable or a mounted system disk, **When** `make-usb.sh` runs, **Then** it refuses with a clear error and never calls `ventoy -i` / never writes to the device.
2. **Given** a removable device and explicit confirmation, **When** `make-usb.sh` runs, **Then** it installs Ventoy (`ventoy -i`) and creates the `ISO/`, `Bootstrap/`, `Installers/`, `Backups/`, `ventoy/` tree and copies `ventoy.json` + `ks.cfg` into place.
3. **Given** `--update`, **When** `make-usb.sh` runs, **Then** it updates Ventoy in place (no wipe).

### User Story 2 - Zero-touch Fedora install with the snapshot-ready layout (Priority: P2)

Selecting the auto-install entry feeds `ks.cfg` to Fedora, which installs unattended with the exact
§10c BTRFS subvolume layout (snapshots actually work) and a minimal base, then hands off to first boot.

**Why this priority**: The zero-touch OS install + correct partition layout is the bonus path and the
foundation the `system` snapshot profile depends on.

**Independent Test**: Lint/inspect `ks.cfg`: it declares the full §10c subvolume set (incl. the
mandatory `var/lib/gdm`), `compress=zstd:1` on every btrfs entry, `/boot` in root, no swap partition,
an ESP, a minimal `%packages`, and a `%post` that installs the first-boot service.

**Acceptance Scenarios**:

1. **Given** `ks.cfg`, **When** inspected, **Then** it provisions subvolumes root→`/`, home→`/home`, the **mandatory writable `var/lib/gdm`**, and non-snapshotted `opt`, `var/cache`, `var/log`, `var/spool`, `var/tmp`, `var/lib/containers`, `var/lib/flatpak`, `var/lib/libvirt`, with `/boot` inside root, **no swap partition** (zram only), `compress=zstd:1` on all btrfs mounts, and an ESP.
2. **Given** `ks.cfg` `%packages`, **When** inspected, **Then** it is minimal (git + the python3/jq the engine needs), not a full desktop bundle beyond the Fedora Workstation environment.

### User Story 3 - First boot finishes the workstation hands-off (Priority: P3)

After the unattended OS install, a first-boot oneshot runs `install.sh --profile full` against the
injected secrets, logs its work, and disables itself so subsequent boots are normal.

**Why this priority**: Completes the zero-touch chain; depends on US2.

**Independent Test**: Inspect the `devboost-firstboot.service` (and the `%post` that installs it): it is
a oneshot that runs `install.sh --profile full --secrets <path>`, logs to
`/var/log/devboost-firstboot.log`, and disables itself after a successful run.

**Acceptance Scenarios**:

1. **Given** the first networked boot, **When** `devboost-firstboot.service` runs, **Then** it executes `install.sh --profile full --secrets <injected secrets.age>`, logs to `/var/log/devboost-firstboot.log`, and on success disables itself (so it never re-runs).
2. **Given** `ventoy.json`, **When** inspected, **Then** it binds `ks.cfg` to the Fedora ISO via `auto_install` and injects `devboost.tar.gz` (dev-boost + secrets) via `injection`, with a sane menu timeout + default image.

### Edge Cases

- **make-usb.sh against the running system disk / a partition / a loop device**: refuse; only a whole removable block device is acceptable.
- **make-usb.sh without confirmation / non-interactive**: do not wipe unless an explicit confirm flag or interactive "yes" is given.
- **ks.cfg custom partitioning must include `compress=zstd:1`** (custom layouts lack it by default) and the **`var/lib/gdm`** subvol (without it, booting a read-only snapshot fails at login).
- **No swap partition** — zram only (a swap partition would break hibernate-less snapshot assumptions and waste disk).
- **firstboot service must disable itself** even if `install.sh` partially fails (so a boot loop of re-installs can't occur) — record the outcome and disable; re-run is a manual action.
- **ventoy.json must be valid JSON** and reference paths that exist in the USB tree.
- **All validation is hermetic** — no real `ventoy -i`, `dd`, mkfs, or disk mutation in tests.

## Clarifications

### Session 2026-06-21 (self-resolved, design doc = oracle)

- Q: USB tree + ventoy.json shape? → A: verbatim design §9.3/§9.4 (ISO/Bootstrap/Installers/Backups/
  ventoy; control timeout+default, auto_install ks.cfg↔Fedora ISO, injection devboost.tar.gz). [FR-001,003]
- Q: Exact BTRFS layout? → A: §10c verbatim — root→/, home→/home, mandatory writable `var/lib/gdm`,
  non-snapshot opt/var/cache/var/log/var/spool/var/tmp/var/lib/{containers,flatpak,libvirt}; /boot in
  root; NO swap (zram only); `compress=zstd:1` on all btrfs mounts; ESP. [FR-004]
- Q: first-boot flow? → A: §9.6 — `%post` installs+enables `devboost-firstboot.service` (oneshot
  `install.sh --profile full --secrets …`, log /var/log/devboost-firstboot.log, self-disable). [FR-005,006]
- Q: make-usb.sh safety? → A: refuse non-removable/system/partition/loop; require explicit confirm;
  `--update` in-place. [FR-002]
- Q: what's committed? → A: scripts/config/kickstart only; ISOs/secrets.age/large binaries NOT in repo
  (synced/provisioned onto the USB out-of-band). [Assumptions]
- Q: how validated? → A: hermetically — stub lsblk/ventoy; assert content + safety behavior; no real
  disk/USB mutation. [FR-007]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `ventoy/make-usb.sh` MUST install Ventoy to a target USB (`ventoy -i`), support `--update` (in-place, no wipe), and lay out the USB tree (`ISO/`, `Bootstrap/`, `Installers/`, `Backups/`, `ventoy/`) copying `ventoy.json` + `ks.cfg` into the right locations.
- **FR-002**: `make-usb.sh` MUST refuse to run against a non-removable disk, a system/mounted disk, a partition, or a loop device, and MUST require explicit confirmation before any destructive operation — never wiping unconfirmed.
- **FR-003**: `ventoy/ventoy.json` MUST be valid JSON binding `ks.cfg` to the Fedora ISO via `auto_install`, injecting `devboost.tar.gz` via `injection`, with a menu timeout + default image (`control`).
- **FR-004**: `ventoy/ks.cfg` MUST provision the §10c BTRFS layout: subvolumes root→`/`, home→`/home`, the mandatory writable `var/lib/gdm`, and non-snapshotted `opt`, `var/cache`, `var/log`, `var/spool`, `var/tmp`, `var/lib/containers`, `var/lib/flatpak`, `var/lib/libvirt`; `/boot` inside root; an ESP; **no swap partition** (zram only); `compress=zstd:1` on all btrfs mounts.
- **FR-005**: `ks.cfg` `%packages` MUST be minimal (Fedora Workstation env + git + python3 + jq — the engine's needs), and its `%post` MUST install + enable `devboost-firstboot.service`.
- **FR-006**: `devboost-firstboot.service` MUST be a oneshot that runs `install.sh --profile full --secrets <path>`, logs to `/var/log/devboost-firstboot.log`, and disables itself after running (no re-run / no boot loop).
- **FR-007**: All artifacts MUST be documented (a recovery runbook) and validated hermetically — tests stub `lsblk`/`ventoy` and assert content/behavior with no real disk/USB mutation.

### Key Entities *(include if data involved)*

- **make-usb.sh**: the USB builder (device-safety guard + tree layout + Ventoy install/update).
- **ventoy.json**: Ventoy control/auto_install/injection config.
- **ks.cfg**: Fedora Kickstart — §10c partitioning + minimal packages + first-boot %post.
- **devboost-firstboot.service**: the self-disabling first-boot bootstrap oneshot.
- **USB tree**: ISO/Bootstrap/Installers/Backups/ventoy layout.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `make-usb.sh` refuses 100% of non-removable/system/partition/loop targets (0 chance of wiping the workstation disk) and only proceeds on a confirmed removable whole-device.
- **SC-002**: `ks.cfg` produces a snapshot-capable system — the `var/lib/gdm` subvol and `compress=zstd:1` are present so booting a read-only snapshot reaches the login screen.
- **SC-003**: The zero-touch path reaches a fully-configured workstation with no interaction beyond (optionally) the one-time NVIDIA MOK screen — first boot runs `install.sh --profile full` and then never re-runs.
- **SC-004**: `ventoy.json` is valid JSON and correctly binds ks.cfg + injection to the Fedora ISO.
- **SC-005**: All artifacts validate green in the hermetic test suite (no real disk operations); the existing suite stays green.

## Assumptions

- **Design doc is the oracle** (hands-free): the USB tree, ventoy.json shape, §10c BTRFS layout, and
  first-boot flow are taken verbatim from design §9/§10c and recorded in Clarifications.
- **Ventoy is the delivery mechanism** (installed once; ISOs copied thereafter); `make-usb.sh` wraps
  `ventoy -i`/`-u` and is the only destructive step, heavily guarded.
- **The Fedora ISO + large binaries are NOT committed** to the repo; `make-usb.sh` references/syncs them
  onto the USB; the repo ships the scripts/config/kickstart only.
- **secrets.age is provisioned onto the USB out-of-band** (never committed), consistent with the secrets
  model; injection unpacks it into the installer for `%post`/first boot.
- **These are artifacts, not engine modules** — no `profiles.toml`/module changes; validated by content
  + behavior tests, hermetically.
- **`/boot` stays in root** for atomic kernel+initramfs snapshots; **zram-only** (no swap partition).
