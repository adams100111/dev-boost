#!/usr/bin/env bash
# modules/nvidia-resign-service/install.sh — boot-time NVIDIA module re-sign service
# (Spec 10, FR-009). After a kernel update the akmod rebuilds the NVIDIA module, which
# must be re-signed (Secure Boot) and CRC32-recompressed before the display manager
# starts. This installs a signing helper + a oneshot unit ordered before display-manager.
# Fedora-only; idempotent (verify-guarded); non-interactive.
#
# Test overrides: DEVBOOST_SBIN_DIR (default /usr/local/sbin),
#                 DEVBOOST_SYSTEMD_SYSTEM_DIR (default /etc/systemd/system).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"

_SBIN_DIR="${DEVBOOST_SBIN_DIR:-/usr/local/sbin}"
_UNIT_DIR="${DEVBOOST_SYSTEMD_SYSTEM_DIR:-/etc/systemd/system}"
_SCRIPT="${_SBIN_DIR}/sign-nvidia-modules"
_UNIT="${_UNIT_DIR}/nvidia-resign.service"

# ---------------------------------------------------------------------------
# Step 1: install the signing helper (always rewritten for idempotent correctness).
# ---------------------------------------------------------------------------
log_info "nvidia-resign-service: installing ${_SCRIPT}"
mkdir -p "${_SBIN_DIR}"
cat > "${_SCRIPT}" <<'SIGN'
#!/usr/bin/env bash
# sign-nvidia-modules — re-sign + CRC32-recompress akmod NVIDIA modules for the
# running kernel. Invoked by nvidia-resign.service before the display manager starts.
set -Eeuo pipefail

KVER="$(uname -r)"
CERT_DER="${MOK_CERT_DER:-/etc/pki/akmods/certs/public_key.der}"
CERT_KEY="${MOK_CERT_KEY:-/etc/pki/akmods/private/private_key.priv}"
SIGNER="$(find /usr/src/kernels/"${KVER}"/scripts/sign-file \
              /lib/modules/"${KVER}"/build/scripts/sign-file 2>/dev/null | head -n1 || true)"

shopt -s nullglob
for ko in /lib/modules/"${KVER}"/extra/nvidia*/*.ko.xz /lib/modules/"${KVER}"/extra/*/nvidia*.ko.xz; do
  [ -e "${ko}" ] || continue
  base="${ko%.xz}"
  # Decompress, (re-)sign, then recompress with a CRC32 integrity check.
  unxz --force "${ko}"
  if [ -n "${SIGNER}" ] && [ -e "${CERT_KEY}" ] && [ -e "${CERT_DER}" ]; then
    "${SIGNER}" sha256 "${CERT_KEY}" "${CERT_DER}" "${base}" || true
  fi
  xz --check=crc32 --force "${base}"
done

depmod -a
SIGN
chmod 0755 "${_SCRIPT}"

# ---------------------------------------------------------------------------
# Step 2: install the oneshot unit, ordered before the display manager.
# ---------------------------------------------------------------------------
log_info "nvidia-resign-service: installing ${_UNIT}"
mkdir -p "${_UNIT_DIR}"
cat > "${_UNIT}" <<UNIT
[Unit]
Description=Re-sign and CRC32-recompress NVIDIA akmod modules
Before=display-manager.service
After=local-fs.target

[Service]
Type=oneshot
ExecStart=${_SCRIPT}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

# ---------------------------------------------------------------------------
# Step 3: enable the unit (idempotent).
# ---------------------------------------------------------------------------
log_info "nvidia-resign-service: enabling nvidia-resign.service"
sudo systemctl enable nvidia-resign.service

log_ok "nvidia-resign-service: re-sign service installed and enabled"
