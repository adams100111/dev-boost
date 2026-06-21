# Contract: hardware-nvidia chain (design §10 verbatim)

All category="hardware", requires include rpmfusion/nvidia-akmod, Fedora-only. Stubbed
akmods/mokutil/kmodgenca/grubby/dracut/depmod/xz/unxz/systemctl/nvidia-ctk.

## nvidia-akmod (FR-007)
- dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda libva-nvidia-driver libva-utils vulkan-tools.
- akmods --force. nouveau blacklist: write /etc/modprobe.d/blacklist-nouveau.conf + grubby --update-kernel=ALL
  --args="rd.driver.blacklist=nouveau nvidia-drm.modeset=1" (honor DEVBOOST_MODPROBE_DIR/grubby stub).
- CRC64→CRC32: for the akmod .ko.xz, unxz then `xz --check=crc32`; idempotent (skip if already crc32 —
  detect via a marker/knob STUB_KO_CRC). depmod -a; dracut --force.
- verify: nvidia.ko present for running kernel (stub: a marker file).
Tests: assert dnf pkgs, akmods --force, grubby args, CRC recompress invoked, dracut --force; idempotent CRC.

## secureboot-mok (FR-008) — MOK state machine
- mokutil --sb-state: 'disabled' → skip+log (verify green). 'enabled':
  enrolled (STUB_MOK_ENROLLED=1) → no-op; queued (STUB_MOK_QUEUED=1) → log 'reboot to finish'; else
  kmodgenca -a (only if /etc/pki/akmods/certs/public_key.der absent) + mokutil --import <der>.
- verify: sb-off OR enrolled OR queued (i.e., not 'needs-import-and-not-done').
Tests: each branch via STUB_SB_STATE/STUB_MOK_ENROLLED/STUB_MOK_QUEUED; --import invoked only in else.

## nvidia-resign-service (FR-009)
- install /usr/local/sbin/sign-nvidia-modules (honor DEVBOOST_SBIN_DIR) + ~ system unit
  nvidia-resign.service (Type=oneshot, Before=display-manager.service); systemctl enable. Idempotent.
- verify: script + unit present (+ enabled best-effort).

## cuda / libva-nvidia-driver / nvidia-container-toolkit (FR-006,010)
- dnf install; nvidia-container-toolkit also runs `nvidia-ctk runtime configure`. verify rpm -q / command -v.
