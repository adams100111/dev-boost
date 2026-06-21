# Feature Specification: system-resilience

**Feature Branch**: `010-system-resilience`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "system-resilience — recovery/hardware-resilience profile + GPU auto-detect + NVIDIA chain."

## User Scenarios & Testing *(mandatory)*

This feature gives the workstation a real **recovery story** (a bad update is a reboot, not a rebuild),
**hardware health & power** management, **OOM protection** that sacrifices a browser tab instead of the
toolchain, and a **GPU that just works** — Intel/AMD cleanly and NVIDIA via the hard-won
akmod/MOK/CRC chain — auto-detected with no flag. It realizes the mission's "GPU auto-detected" and
"bad update recoverable by reboot" promises (design §6.3, §6.1/§10, §11).

### User Story 1 - A bad update is a reboot, not a rebuild (Priority: P1)

After install, the machine takes automatic Btrfs snapshots before/after every package transaction and
exposes a "Fedora snapshots" boot menu, so a broken update is recovered by rebooting into the
pre-update snapshot.

**Why this priority**: The core resilience promise; everything else hardens around it. Independently
valuable and testable.

**Independent Test**: With stubbed dnf/systemctl, install the snapshot modules; assert snapper is
configured, the dnf snapshot hook is installed, and grub-btrfs is enabled so a snapshot boot entry is
generated; re-running is a no-op.

**Acceptance Scenarios**:

1. **Given** a Btrfs machine, **When** the snapshot modules install, **Then** snapper is configured for the root config, the dnf snapshot plugin auto-snapshots before/after transactions, and grub-btrfs adds a snapshots boot menu; each module verifies green.
2. **Given** they are already installed, **When** re-run, **Then** every module skips (idempotent).
3. **Given** a non-Fedora OS, **When** attempted, **Then** the engine reports each module unsupported.

### User Story 2 - Hardware stays healthy, powered, and patched (Priority: P2)

The laptop gets firmware updates (fwupd/LVFS), Btrfs scrub/balance maintenance, disk-health monitoring
(smartd), thermal management (thermald) + power profiles, and security-only auto-updates — safe because
snapshots provide rollback.

**Why this priority**: Day-2 durability layered on the snapshot safety net (US1).

**Independent Test**: Install each maintenance module (stubbed); assert the service/timer is enabled and
verify is green; security-only auto-update config excludes full upgrades.

**Acceptance Scenarios**:

1. **Given** the system profile installs, **When** complete, **Then** fwupd, btrfsmaintenance (scrub/balance timers), smartmontools (smartd), thermald, power-profiles-daemon, dnf-automatic-security, and restic-backup are each installed/enabled and verify green.
2. **Given** dnf-automatic, **When** configured, **Then** only security updates auto-apply (not arbitrary upgrades).
3. **Given** restic-backup, **When** installed, **Then** a sample repo config + a systemd backup timer are present (no secrets committed).

### User Story 3 - A runaway build can't freeze the machine (Priority: P3)

earlyoom is configured to protect dev processes (dockerd, dotnet, dcp*, sshd, code, gnome-shell) and
prefer killing memory-hog desktop apps (browsers, Electron/QtWebEngine), so an OOM event sacrifices a
browser tab, not your toolchain (design §8b).

**Why this priority**: Directly addresses the audit-found starvation class; independent slice.

**Independent Test**: Install earlyoom (stubbed); assert the service is enabled and its config encodes
the protect-dev / prefer-desktop-apps preference patterns.

**Acceptance Scenarios**:

1. **Given** earlyoom installs, **When** configured, **Then** its preferred-kill (`--prefer`) pattern targets browser/Electron processes and its avoid (`--avoid`) pattern protects dockerd/dotnet/dcp/sshd/code/gnome-shell, and the service is enabled; verify green; idempotent.

### User Story 4 - The right GPU driver path is chosen automatically (Priority: P4)

`gpu-detect` (in `full`) reads the GPU vendor from the hardware and selects the correct path with no
profile flag: Intel/AMD use the clean open path; NVIDIA triggers the `hardware-nvidia` chain.

**Why this priority**: The "GPU auto-detected, no flag" mission promise; composes US5.

**Independent Test**: With the lspci stub set to intel/amd/nvidia, run gpu-detect; assert it reports the
detected vendor and selects the matching path (NVIDIA → recommends/triggers hardware-nvidia; Intel/AMD →
open path), and an unrecognized vendor is reported clearly.

**Acceptance Scenarios**:

1. **Given** an NVIDIA GPU, **When** gpu-detect runs, **Then** it detects NVIDIA and selects the hardware-nvidia path.
2. **Given** an Intel or AMD GPU, **When** gpu-detect runs, **Then** it selects the open VA-API/mesa path and does NOT pull NVIDIA packages.
3. **Given** a hybrid Intel+NVIDIA, **When** gpu-detect runs, **Then** it selects the NVIDIA path (discrete present) while leaving the integrated path intact.

### User Story 5 - NVIDIA + CUDA work and survive kernel updates (Priority: P5)

On an NVIDIA machine the `hardware-nvidia` chain installs the akmod driver + CUDA + VA-API, handles
Secure-Boot MOK signing idempotently, applies the CRC64→CRC32 akmod fix, blacklists nouveau, and
installs a boot-time re-sign service so kernel updates never silently break the GPU. The only
interactive moment is the one-time MOK enrollment screen when Secure Boot is on.

**Why this priority**: High-value but hardware-specific and the most complex; depends on US4 detection.

**Independent Test**: With stubbed akmods/mokutil/kmodgenca/grubby/dracut/xz/systemctl, install the
chain; assert each non-obvious fix is applied exactly (MOK state machine branches, CRC32 recompress,
nouveau blacklist, resign service), and that with Secure Boot off signing is skipped.

**Acceptance Scenarios**:

1. **Given** an NVIDIA GPU, **When** nvidia-akmod installs, **Then** akmod-nvidia + CUDA + libva-nvidia-driver (renamed from nvidia-vaapi-driver) + libva-utils/vulkan-tools are installed, `akmods --force` runs, nouveau is blacklisted (modprobe.d + grubby kernel args), the akmod module is recompressed CRC64→CRC32, and depmod + initramfs are regenerated.
2. **Given** Secure Boot ON and the key not yet enrolled, **When** secureboot-mok runs, **Then** it imports the akmods public key via mokutil (generating the CA only if absent) and stops at the one-time enrollment step; **Given** Secure Boot OFF, signing is skipped; **Given** the key already enrolled, it is a no-op.
3. **Given** a kernel update, **When** the nvidia-resign service runs at boot, **Then** it re-signs + CRC32-recompresses the akmod modules before the display manager starts; idempotent no-op once correct.
4. **Given** containers need the GPU, **When** nvidia-container-toolkit installs, **Then** `nvidia-ctk runtime configure` wires the container runtime.

### User Story 6 - Diagnose a broken GPU quickly (Priority: P6)

`devboost doctor --gpu` runs a focused diagnostic (driver loadable, nouveau blacklisted, initramfs
correct, module signature present, kernel taint/lockdown/pkcs#7 scan) so a GPU problem is pinpointed
without manual archaeology.

**Why this priority**: Operational hardening on top of US5; an engine doctor extension.

**Independent Test**: Run `doctor --gpu` (stubbed modprobe/dmesg); assert it reports each check and
exits non-zero when a check fails (e.g., nouveau not blacklisted).

**Acceptance Scenarios**:

1. **Given** a healthy NVIDIA setup, **When** `devboost doctor --gpu` runs, **Then** it reports driver/nouveau/initramfs/signature checks green and exits zero.
2. **Given** a broken setup (driver won't load / nouveau present), **When** `devboost doctor --gpu` runs, **Then** it names the failing check and exits non-zero. Plain `devboost doctor` (no `--gpu`) keeps its existing behavior.

### User Story 7 - Power users can opt into heavier editors (Priority: P7)

`optional-editors` (not in `full`) installs Neovim/LazyVim + JetBrains Toolbox (PhpStorm/Rider) for
those who want them.

**Why this priority**: Convenience, off the critical path; opt-in.

**Independent Test**: Install `optional-editors` (stubbed); assert Neovim + JetBrains Toolbox modules
install and verify; not present in `full`.

**Acceptance Scenarios**:

1. **Given** `--profile optional-editors`, **When** installed, **Then** Neovim (+LazyVim bootstrap) and JetBrains Toolbox are installed and verify green; **And** they are NOT part of `full`.

### Edge Cases

- **Non-Btrfs root**: snapshot modules require Btrfs; on a non-Btrfs root they report a clear, named failure (not silent success).
- **Secure Boot OFF**: NVIDIA signing/MOK is skipped entirely (no enrollment needed).
- **MOK already queued** (`--list-new`): secureboot-mok does not re-import; it reports "reboot to finish enrollment".
- **No NVIDIA GPU but hardware-nvidia selected explicitly**: modules still install but `doctor --gpu` / verify reflect absence; gpu-detect would not have selected it.
- **Unrecognized GPU vendor**: gpu-detect reports it clearly (mirrors va-hwaccel) and does not guess a driver.
- **dnf-automatic must NOT auto-apply full upgrades** — security-only, to keep pinned dev tools controlled.
- **earlyoom avoid/prefer patterns must not be empty** — protecting nothing would defeat the purpose.
- **CRC fix idempotency**: re-running on an already-CRC32 module is a no-op (don't double-process).
- **All hardware/driver/btrfs/MOK actions are stubbed in tests** — no real mutation.

## Clarifications

### Session 2026-06-21 (self-resolved, design doc = oracle)

- Q: Package set + fix sequence for NVIDIA? → A: verbatim from design §10 (akmod-nvidia +
  xorg-x11-drv-nvidia-cuda + libva-nvidia-driver + libva-utils + vulkan-tools; akmods --force;
  nouveau blacklist; CRC64→CRC32 recompress; depmod + dracut; resign service; nvidia-ctk). [FR-006..010]
- Q: MOK posture? → A: Fedora's own akmods CA; idempotent state machine; one-time enrollment is the
  sole interactive step (SB on only). [FR-008]
- Q: dnf-automatic scope? → A: `upgrade_type = security` (security-only; snapper covers the rest). [FR-002]
- Q: earlyoom policy? → A: `--avoid` dockerd|dotnet|dcp|sshd|code|gnome-shell; `--prefer` browsers/
  Electron/QtWebEngine (design §8b). [FR-004]
- Q: gpu-detect composition? → A: in `full`; NVIDIA → hardware-nvidia path, Intel/AMD → open VA-API/mesa
  (reuse Spec 5 va-hwaccel); unrecognized reported. NVIDIA packages live only in `hardware-nvidia`. [FR-005]
- Q: doctor --gpu? → A: additive engine flag; plain `doctor` unchanged; checks modprobe/nouveau/
  initramfs/signature/dmesg. [FR-011]
- Q: optional-editors membership? → A: opt-in, NOT in `full` (Neovim/LazyVim + JetBrains Toolbox). [FR-012]
- Q: snapshot prerequisite? → A: Btrfs root assumed; non-Btrfs → clear named failure. [Edge Cases]

No external version verification needed beyond the design-confirmed `libva-nvidia-driver` rename.

- Q: `full` membership for `system`/`gpu-detect`? → A: the real `profiles.toml` has **no `full`
  profile yet** (its canonical composition is deferred to a later spec). So `gpu-detect` is placed in
  the **`system`** profile; since the design puts `system` in `full`, gpu-detect is included
  transitively once `full` is defined later. No `full` is invented in this spec. [FR-003, FR-005]

## Requirements *(mandatory)*

### Functional Requirements

**system recovery + maintenance (US1–US2)**

- **FR-001**: The system MUST provide snapshot-recovery modules — snapper (root config), snapper-dnf-hook (auto-snapshot before/after dnf via the dnf snapper plugin), grub-btrfs (snapshots boot menu), btrfs-assistant (GUI) — each Fedora-only, idempotent, verify-guarded.
- **FR-002**: The system MUST provide maintenance/health modules — btrfsmaintenance (scrub/balance timers), fwupd, power-profiles-daemon, thermald, smartmontools (smartd), dnf-automatic-security (security-only auto-updates), restic-backup (sample config + timer, no secrets committed) — each installed/enabled + verify-guarded.
- **FR-003**: A `system` profile MUST aggregate all recovery + maintenance + earlyoom modules; `system` MUST be part of `full`.

**OOM protection (US3)**

- **FR-004**: The system MUST provide an `earlyoom` module whose configuration protects dev processes (dockerd, dotnet, dcp*, sshd, code, gnome-shell) and prefers killing desktop memory hogs (browsers, Electron/QtWebEngine), with the service enabled; idempotent + verify-guarded.

**GPU auto-detect + NVIDIA (US4–US5)**

- **FR-005**: The system MUST provide a `gpu-detect` module (in `full`) that detects the GPU vendor from hardware and selects the correct driver path with no flag: NVIDIA → the hardware-nvidia path; Intel/AMD → the open path; unrecognized vendor reported clearly (mirrors the existing va-hwaccel detection).
- **FR-006**: The system MUST provide a `hardware-nvidia` profile = rpmfusion (reused) + nvidia-akmod + cuda + libva-nvidia-driver (renamed from nvidia-vaapi-driver) + secureboot-mok + nvidia-resign-service + nvidia-container-toolkit.
- **FR-007**: `nvidia-akmod` MUST install akmod-nvidia + xorg-x11-drv-nvidia-cuda + libva-nvidia-driver + libva-utils + vulkan-tools, run `akmods --force`, blacklist nouveau (modprobe.d + grubby `rd.driver.blacklist=nouveau nvidia-drm.modeset=1`), apply the CRC64→CRC32 akmod recompress (unxz then `xz --check=crc32`, preserving the signature, idempotent), regenerate depmod + initramfs, and verify `nvidia.ko` for the running kernel.
- **FR-008**: `secureboot-mok` MUST implement the idempotent MOK state machine: SB off → skip; key enrolled → no-op; queued → report reboot-to-finish; else import the akmods public key via mokutil (generate the CA only if genuinely absent), using Fedora's own akmods signing infra; the one-time enrollment screen is the only interactive step.
- **FR-009**: `nvidia-resign-service` MUST install a boot-time oneshot (`Before=display-manager.service`) that re-signs + CRC32-recompresses the akmod modules for each new kernel; idempotent no-op once correct.
- **FR-010**: `nvidia-container-toolkit` MUST install the toolkit and run `nvidia-ctk runtime configure`.

**doctor --gpu (US6) + optional-editors (US7)**

- **FR-011**: The engine MUST extend `doctor` with a `--gpu` diagnostic (modprobe load test, nouveau-blacklist + initramfs check, module-signature check, dmesg taint/lockdown/pkcs#7 scan) reporting each check and exiting non-zero on failure; plain `doctor` behavior is unchanged.
- **FR-012**: The system MUST provide an `optional-editors` profile (Neovim/LazyVim + JetBrains Toolbox) that is NOT part of `full`.

**Cross-cutting**

- **FR-013**: All actions MUST be unattended except the one-time NVIDIA MOK enrollment screen (only when Secure Boot is on); idempotent + verify-guarded; Fedora-only `[install]` ⇒ unsupported elsewhere by data.
- **FR-014**: The work MUST be built test-first and keep the existing suite green, extending the harness backward-compatibly and stubbing ALL system calls (dnf/rpm/akmods/mokutil/kmodgenca/grubby/dracut/depmod/modprobe/systemctl/nvidia-ctk/unxz/xz/lspci/dmesg) — no real hardware/driver/btrfs/firmware/MOK mutation.

### Key Entities *(include if data involved)*

- **System module**: one resilience/maintenance unit (package + service/timer + verify).
- **Snapshot stack**: snapper config + dnf hook + grub-btrfs boot menu.
- **earlyoom policy**: the avoid (protect) + prefer (kill) process patterns.
- **GPU detection result**: vendor(s) from hardware → selected driver path.
- **NVIDIA chain state**: akmod module (+ CRC format), MOK enrollment state, resign service, container runtime config.
- **GPU diagnostic report**: per-check results from `doctor --gpu`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After install, a "Fedora snapshots" boot entry exists and a package transaction produces pre/post snapshots — a bad update is recoverable by a single reboot.
- **SC-002**: 100% of `system` maintenance services/timers are enabled and verify green; dnf-automatic applies security updates only (0 arbitrary upgrades).
- **SC-003**: Under memory pressure, earlyoom kills a desktop memory hog before any protected dev process (0 protected-process kills in the configured policy).
- **SC-004**: GPU vendor is selected automatically with no flag — NVIDIA → NVIDIA path, Intel/AMD → open path — for 100% of recognized vendors; unrecognized vendors are reported, never silently mis-driven.
- **SC-005**: On NVIDIA, the driver loads and survives a kernel update without manual intervention (resign service handles it); the only interactive moment is the one-time MOK enrollment when Secure Boot is on.
- **SC-006**: `devboost doctor --gpu` correctly reports green on a healthy setup and non-zero (naming the failed check) on a broken one.
- **SC-007**: The full bats suite stays green; every new module/diagnostic is covered by stub-only tests (no real hardware mutation).

## Assumptions

- **Design doc is the oracle** (hands-free): all decisions — package names, the NVIDIA fix sequence, earlyoom patterns, profile composition — are taken from design §6.1/§6.3/§10/§11 and recorded in Clarifications. `libva-nvidia-driver` (renamed from `nvidia-vaapi-driver`) is confirmed by the design.
- **Btrfs root** is assumed (Fedora Workstation default); snapshot modules require it and fail clearly otherwise.
- **gpu-detect composition**: gpu-detect is in `full` and, on NVIDIA hardware, selects/triggers the `hardware-nvidia` chain; the actual NVIDIA packages live in the `hardware-nvidia` profile so a non-NVIDIA machine never pulls them. Intel/AMD acceleration largely reuses the Spec 5 `va-hwaccel` open path.
- **MOK security model**: uses Fedora's own akmods signing key/CA (no hand-rolled CA); passphrase-less unattended except the unavoidable one-time firmware enrollment screen.
- **dnf-automatic** is configured `upgrade_type = security` (security-only) because snapper provides the rollback safety net for everything else.
- **restic-backup** ships a sample repo config + timer only; real backup credentials are provisioned out-of-band (never committed), consistent with the secrets model.
- **doctor --gpu** is an additive engine flag; plain `doctor` is unchanged (engine-feature, test-first).
- **optional-editors** is opt-in and excluded from `full` to keep the default install lean.
