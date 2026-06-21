# Phase 0 Research: system-resilience

Decisions grounded in design §6.1/§6.3/§10/§11 + constitution (oracle; hands-free). Mostly data
modules (Principle I); `doctor --gpu` is an additive engine flag (Principle V TDD). No new external
tools needing context7 beyond the design-confirmed `libva-nvidia-driver` rename.

## Decisions

- **D0. One module per concern**, `category="system"` (resilience/maintenance) or `category="hardware"`
  (nvidia chain), Fedora-only `[install]`, idempotent + verify-guarded. `system` profile ∈ `full`;
  `hardware-nvidia` + `optional-editors` are opt-in profiles.
- **D1. GPU detection reuses Spec 5** (`modules/va-hwaccel` lspci pattern + `STUB_GPU_VENDOR`). `gpu-detect`
  (in `full`) detects vendor and selects the path: NVIDIA → the `hardware-nvidia` chain; Intel/AMD →
  the open VA-API/mesa path (already delivered by `va-hwaccel`); unrecognized → reported, never guessed.
  NVIDIA packages live ONLY in `hardware-nvidia` so non-NVIDIA machines never pull them.
- **D2. NVIDIA chain (design §10, verbatim non-obvious fixes):**
  - `nvidia-akmod`: `dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda libva-nvidia-driver libva-utils
    vulkan-tools`; `akmods --force`; nouveau blacklist (`/etc/modprobe.d/blacklist-nouveau.conf` +
    grubby `rd.driver.blacklist=nouveau nvidia-drm.modeset=1`); **CRC64→CRC32 recompress** of the akmod
    `.ko.xz` (unxz → `xz --check=crc32`, signature preserved, idempotent: skip if already crc32);
    `depmod -a` + `dracut --force`; verify `nvidia.ko` present for the running kernel.
  - `secureboot-mok`: `mokutil --sb-state` → off=skip; `--test-key`/enrolled=no-op; `--list-new`
    queued=report reboot; else `kmodgenca -a` (only if CA absent) + `mokutil --import
    /etc/pki/akmods/certs/public_key.der`. One-time enrollment screen = sole interactive step.
  - `nvidia-resign-service`: install `/usr/local/sbin/sign-nvidia-modules` + a oneshot unit
    `Before=display-manager.service` that re-signs + crc32-recompresses per new kernel; enable it.
  - `cuda`: `xorg-x11-drv-nvidia-cuda` (folded with akmod) or `cuda` metapackage; `libva-nvidia-driver`
    is its own tiny module (renamed pkg). `nvidia-container-toolkit`: install + `nvidia-ctk runtime configure`.
- **D3. system modules** map to packages/services: snapper, `python3-dnf-plugin-snapper` (snapper-dnf-hook),
  grub-btrfs, btrfs-assistant, btrfsmaintenance, fwupd, power-profiles-daemon, thermald, smartmontools
  (`smartd`), dnf-automatic (`/etc/dnf/automatic.conf` `upgrade_type=security` + enable timer),
  restic-backup (sample repo conf + `restic-backup.timer`). earlyoom: `/etc/default/earlyoom`
  `EARLYOOM_ARGS='--avoid '\''(^|/)(dockerd|dotnet|dcp|sshd|code|gnome-shell)$'\'' --prefer
  '\''(^|/)(firefox|chrome|chromium|electron|QtWebEngine|brave|slack|discord)$'\'''` + enable service.
- **D4. doctor --gpu** (bin/devboost): `cmd_doctor` gains a `--gpu` branch (new `lib` helper or inline)
  running modprobe-load test, nouveau-blacklist check, initramfs check, module-signature check, and a
  dmesg taint/lockdown/pkcs#7 scan; each reported; non-zero on any failure. Plain `doctor` unchanged.

## Testing (no real hardware/driver/btrfs/MOK)

Extend `tests/fixtures/base/stubs.bash` (backward-compatible): add stubs for `akmods`, `mokutil`
(`--sb-state`→STUB_SB_STATE, `--list-new`/enrolled→STUB_MOK_ENROLLED, `--import` logs), `kmodgenca`,
`grubby`, `dracut`, `depmod`, `modprobe` (load test → STUB_MODPROBE_FAIL), `nvidia-ctk`, `unxz`/`xz`
(CRC recompress: operate on a fake .ko.xz marker), `dmesg` (→STUB_DMESG). Reuse `lspci`/STUB_GPU_VENDOR,
`dnf`/`rpm`/`systemctl`/`grub2-mkconfig`. Each module: install cmd attempted (assert log) + verify
GREEN + idempotent + unsupported-OS. NVIDIA: assert each fix branch (MOK states, CRC32, nouveau, resign
unit). doctor --gpu: green/red per stub state. No real mutation.

## Outcome
No unresolved unknowns (all in spec §Clarifications). Ready for Phase 1.
