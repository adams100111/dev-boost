#!/usr/bin/env bash
# modules/nvidia-akmod/install.sh — NVIDIA akmod driver chain (Spec 10, FR-007).
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (verify-guarded by the engine); non-interactive; Fedora-only.
#
# Steps:
#   1. dnf install akmod-nvidia + cuda + libva-nvidia-driver + libva-utils + vulkan-tools.
#   2. akmods --force (build the kernel module against the running kernel).
#   3. nouveau blacklist: write blacklist-nouveau.conf + grubby kernel args.
#   4. CRC64→CRC32 recompress of the akmod .ko.xz (kernels reject CRC64 xz modules);
#      idempotent via a <ko>.crc32 sentinel.
#   5. depmod -a + dracut --force (rebuild initramfs).
#
# Test overrides:
#   DEVBOOST_MODPROBE_DIR (default /etc/modprobe.d), DEVBOOST_AKMOD_KO (a specific .ko.xz).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

_MODPROBE_DIR="${DEVBOOST_MODPROBE_DIR:-/etc/modprobe.d}"

# ---------------------------------------------------------------------------
# Step 1: install driver + CUDA + VA-API + diagnostics packages.
# ---------------------------------------------------------------------------
log_info "nvidia-akmod: installing akmod-nvidia + cuda + va-api packages"
dnf_install akmod-nvidia xorg-x11-drv-nvidia-cuda libva-nvidia-driver libva-utils vulkan-tools

# ---------------------------------------------------------------------------
# Step 2: build the akmod against the running kernel.
# ---------------------------------------------------------------------------
log_info "nvidia-akmod: building kernel module (akmods --force)"
sudo akmods --force

# ---------------------------------------------------------------------------
# Step 3: blacklist nouveau (modprobe conf + kernel cmdline).
# ---------------------------------------------------------------------------
_blacklist="${_MODPROBE_DIR}/blacklist-nouveau.conf"
if [[ ! -f "${_blacklist}" ]] || ! grep -q '^blacklist nouveau$' "${_blacklist}"; then
  log_info "nvidia-akmod: writing nouveau blacklist ${_blacklist}"
  mkdir -p "${_MODPROBE_DIR}"
  printf 'blacklist nouveau\noptions nouveau modeset=0\n' > "${_blacklist}"
else
  log_skip "nvidia-akmod: nouveau blacklist already present"
fi

log_info "nvidia-akmod: setting kernel args (rd.driver.blacklist=nouveau nvidia-drm.modeset=1)"
sudo grubby --update-kernel=ALL --args="rd.driver.blacklist=nouveau nvidia-drm.modeset=1"

# ---------------------------------------------------------------------------
# Step 4: CRC64→CRC32 recompress of the akmod .ko.xz.
# Newer akmod builds may emit xz streams with a CRC64 integrity check, which
# the kernel module loader rejects. Recompress with CRC32. Idempotent: a
# <ko>.crc32 sentinel marks a module already converted.
# ---------------------------------------------------------------------------
_ko="${DEVBOOST_AKMOD_KO:-}"
if [[ -z "${_ko}" ]]; then
  # Production: locate the freshly built nvidia akmod .ko.xz for the running kernel.
  _ko="$(find "/lib/modules/$(uname -r)" -name 'nvidia*.ko.xz' 2>/dev/null | head -n1 || true)"
fi

if [[ -n "${_ko}" && -e "${_ko}" ]]; then
  _sentinel="${_ko}.crc32"
  if [[ -e "${_sentinel}" ]]; then
    log_skip "nvidia-akmod: ${_ko} already CRC32 (sentinel present)"
  else
    log_info "nvidia-akmod: recompressing ${_ko} with CRC32"
    _dir="$(dirname "${_ko}")"
    _base="$(basename "${_ko}" .xz)"
    ( cd "${_dir}" && unxz --force "${_ko}" && xz --check=crc32 --force "${_base}" )
    : > "${_sentinel}"
  fi
else
  log_warn "nvidia-akmod: no akmod .ko.xz found to recompress (skipping CRC fix)"
fi

# ---------------------------------------------------------------------------
# Step 5: refresh module deps + rebuild initramfs.
# ---------------------------------------------------------------------------
log_info "nvidia-akmod: depmod -a + dracut --force"
sudo depmod -a
sudo dracut --force

log_ok "nvidia-akmod: NVIDIA akmod driver installed"
