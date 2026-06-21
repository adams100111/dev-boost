load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Spec 10: hardware-nvidia chain. All modules category="hardware", Fedora-only [install],
# idempotent, verify-guarded. Kernel/NVIDIA/MOK tooling is stubbed via
# base_install_kernel_stubs (STUB_KERNEL_LOG); dnf/rpm/systemctl come from base_setup.

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  base_install_kernel_stubs

  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"

  # Test override dirs — scratch paths so nothing real is touched.
  export DEVBOOST_MODPROBE_DIR="${BATS_TEST_TMPDIR}/modprobe.d"
  export DEVBOOST_MOK_CERT="${BATS_TEST_TMPDIR}/pki/public_key.der"
  export DEVBOOST_SBIN_DIR="${BATS_TEST_TMPDIR}/sbin"
  export DEVBOOST_SYSTEMD_SYSTEM_DIR="${BATS_TEST_TMPDIR}/systemd-system"
  export DEVBOOST_AKMOD_KO="${BATS_TEST_TMPDIR}/nvidia.ko.xz"
  mkdir -p "${DEVBOOST_MODPROBE_DIR}" "${BATS_TEST_TMPDIR}/pki" \
           "${DEVBOOST_SBIN_DIR}" "${DEVBOOST_SYSTEMD_SYSTEM_DIR}"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run a module's install.sh directly (bash with env), like ssh-setup.bats.
# Avoids the full engine closure (which would try to dnf-install docker etc).
# ---------------------------------------------------------------------------
_run_install() {
  local module="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_KERNEL_LOG='${STUB_KERNEL_LOG}'
    export STUB_SB_STATE='${STUB_SB_STATE:-}'
    export STUB_MOK_ENROLLED='${STUB_MOK_ENROLLED:-}'
    export STUB_MOK_QUEUED='${STUB_MOK_QUEUED:-}'
    export DEVBOOST_MODPROBE_DIR='${DEVBOOST_MODPROBE_DIR}'
    export DEVBOOST_MOK_CERT='${DEVBOOST_MOK_CERT}'
    export DEVBOOST_SBIN_DIR='${DEVBOOST_SBIN_DIR}'
    export DEVBOOST_SYSTEMD_SYSTEM_DIR='${DEVBOOST_SYSTEMD_SYSTEM_DIR}'
    export DEVBOOST_AKMOD_KO='${DEVBOOST_AKMOD_KO}'
    bash '${DEVBOOST_ROOT}/modules/${module}/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Manifest / wiring assertions
# ---------------------------------------------------------------------------

@test "all hardware-nvidia modules declare category=hardware" {
  for m in nvidia-akmod cuda libva-nvidia-driver secureboot-mok \
           nvidia-resign-service nvidia-container-toolkit; do
    run bash -c "
      export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
      export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
      source '${DEVBOOST_ROOT}/lib/log.sh'
      source '${DEVBOOST_ROOT}/lib/toml.sh'
      source '${DEVBOOST_ROOT}/lib/os.sh'
      source '${DEVBOOST_ROOT}/lib/module.sh'
      module_field '${m}' '.category'
    "
    [ "$status" -eq 0 ]
    [ "$output" = "hardware" ]
  done
}

@test "nvidia-akmod requires rpmfusion" {
  run _module_install_cmd nvidia-akmod fedora fedora
  [ "$status" -eq 0 ]
  run bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires nvidia-akmod
  "
  [[ "$output" == *"rpmfusion"* ]]
}

@test "cuda/libva/resign/secureboot require nvidia-akmod; container also requires docker" {
  for m in cuda libva-nvidia-driver secureboot-mok nvidia-resign-service; do
    run bash -c "
      export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
      export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
      source '${DEVBOOST_ROOT}/lib/log.sh'
      source '${DEVBOOST_ROOT}/lib/toml.sh'
      source '${DEVBOOST_ROOT}/lib/os.sh'
      source '${DEVBOOST_ROOT}/lib/module.sh'
      module_requires ${m}
    "
    [[ "$output" == *"nvidia-akmod"* ]]
  done
  run bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires nvidia-container-toolkit
  "
  [[ "$output" == *"nvidia-akmod"* ]]
  [[ "$output" == *"docker"* ]]
}

@test "unsupported OS: install cmd is empty for every nvidia module" {
  for m in nvidia-akmod cuda libva-nvidia-driver secureboot-mok \
           nvidia-resign-service nvidia-container-toolkit; do
    run _module_install_cmd "${m}" ubuntu debian
    [ "$status" -eq 0 ]
    [ -z "$output" ]
  done
}

# ---------------------------------------------------------------------------
# nvidia-akmod (FR-007)
# ---------------------------------------------------------------------------

@test "nvidia-akmod: installs the 5 packages" {
  : > "${DEVBOOST_AKMOD_KO}"
  run _run_install nvidia-akmod
  [ "$status" -eq 0 ]
  dnf="$(cat "${STUB_DNF_LOG}")"
  [[ "$dnf" == *"akmod-nvidia"* ]]
  [[ "$dnf" == *"xorg-x11-drv-nvidia-cuda"* ]]
  [[ "$dnf" == *"libva-nvidia-driver"* ]]
  [[ "$dnf" == *"libva-utils"* ]]
  [[ "$dnf" == *"vulkan-tools"* ]]
}

@test "nvidia-akmod: runs akmods --force" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  grep -q 'akmods --force' "${STUB_KERNEL_LOG}"
}

@test "nvidia-akmod: writes nouveau blacklist conf" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  [ -f "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf" ]
  grep -q 'blacklist nouveau' "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
  grep -q 'options nouveau modeset=0' "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
}

@test "nvidia-akmod: sets grubby nouveau/nvidia kernel args" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  grubby="$(grep '^grubby ' "${STUB_KERNEL_LOG}")"
  [[ "$grubby" == *"--update-kernel=ALL"* ]]
  [[ "$grubby" == *"rd.driver.blacklist=nouveau"* ]]
  [[ "$grubby" == *"nvidia-drm.modeset=1"* ]]
}

@test "nvidia-akmod: CRC64->CRC32 recompress invoked on the ko" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  grep -q 'unxz' "${STUB_KERNEL_LOG}"
  grep -q 'xz --check=crc32' "${STUB_KERNEL_LOG}"
}

@test "nvidia-akmod: CRC recompress is idempotent (second run skips)" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  : > "${STUB_KERNEL_LOG}"   # reset to observe only the second run
  _run_install nvidia-akmod
  run grep -c 'xz --check=crc32' "${STUB_KERNEL_LOG}"
  [ "$output" = "0" ]
}

@test "nvidia-akmod: runs depmod -a and dracut --force" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  grep -q 'depmod -a' "${STUB_KERNEL_LOG}"
  grep -q 'dracut --force' "${STUB_KERNEL_LOG}"
}

@test "nvidia-akmod: verify GREEN after install (marker present)" {
  : > "${DEVBOOST_AKMOD_KO}"
  _run_install nvidia-akmod
  run bash -c "
    export DEVBOOST_AKMOD_KO='${DEVBOOST_AKMOD_KO}'
    bash '${DEVBOOST_ROOT}/modules/nvidia-akmod/verify.sh'
  "
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# secureboot-mok (FR-008) — MOK state machine
# ---------------------------------------------------------------------------

@test "secureboot-mok: SecureBoot disabled -> skip, no --import" {
  export STUB_SB_STATE="disabled"
  run _run_install secureboot-mok
  [ "$status" -eq 0 ]
  run grep -c 'mokutil --import' "${STUB_KERNEL_LOG}"
  [ "$output" = "0" ]
}

@test "secureboot-mok: enabled + already enrolled -> no-op, no --import" {
  export STUB_SB_STATE="enabled"
  export STUB_MOK_ENROLLED="1"
  run _run_install secureboot-mok
  [ "$status" -eq 0 ]
  run grep -c 'mokutil --import' "${STUB_KERNEL_LOG}"
  [ "$output" = "0" ]
}

@test "secureboot-mok: enabled + queued -> reports reboot, no --import" {
  export STUB_SB_STATE="enabled"
  export STUB_MOK_QUEUED="1"
  run _run_install secureboot-mok
  [ "$status" -eq 0 ]
  [[ "$output" == *"reboot"* ]]
  run grep -c 'mokutil --import' "${STUB_KERNEL_LOG}"
  [ "$output" = "0" ]
}

@test "secureboot-mok: enabled + neither -> mokutil --import invoked" {
  export STUB_SB_STATE="enabled"
  run _run_install secureboot-mok
  [ "$status" -eq 0 ]
  grep -q 'mokutil --import' "${STUB_KERNEL_LOG}"
}

@test "secureboot-mok: enabled + neither + no cert -> kmodgenca -a invoked" {
  export STUB_SB_STATE="enabled"
  rm -f "${DEVBOOST_MOK_CERT}"
  _run_install secureboot-mok
  grep -q 'kmodgenca -a' "${STUB_KERNEL_LOG}"
}

@test "secureboot-mok: enabled + neither + cert present -> kmodgenca skipped" {
  export STUB_SB_STATE="enabled"
  : > "${DEVBOOST_MOK_CERT}"
  _run_install secureboot-mok
  run grep -c 'kmodgenca' "${STUB_KERNEL_LOG}"
  [ "$output" = "0" ]
}

@test "secureboot-mok: verify GREEN when SecureBoot disabled" {
  export STUB_SB_STATE="disabled"
  run bash -c "
    export PATH='${PATH}'
    export STUB_KERNEL_LOG='${STUB_KERNEL_LOG}'
    export STUB_SB_STATE='disabled'
    bash '${DEVBOOST_ROOT}/modules/secureboot-mok/verify.sh'
  "
  [ "$status" -eq 0 ]
}

@test "secureboot-mok: verify GREEN when enrolled" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_KERNEL_LOG='${STUB_KERNEL_LOG}'
    export STUB_SB_STATE='enabled'
    export STUB_MOK_ENROLLED='1'
    bash '${DEVBOOST_ROOT}/modules/secureboot-mok/verify.sh'
  "
  [ "$status" -eq 0 ]
}

@test "secureboot-mok: verify RED when enabled + not enrolled + not queued" {
  run bash -c "
    export PATH='${PATH}'
    export STUB_KERNEL_LOG='${STUB_KERNEL_LOG}'
    export STUB_SB_STATE='enabled'
    bash '${DEVBOOST_ROOT}/modules/secureboot-mok/verify.sh'
  "
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# nvidia-resign-service (FR-009)
# ---------------------------------------------------------------------------

@test "nvidia-resign-service: installs sign script + oneshot unit, enables it" {
  run _run_install nvidia-resign-service
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_SBIN_DIR}/sign-nvidia-modules" ]
  [ -x "${DEVBOOST_SBIN_DIR}/sign-nvidia-modules" ]
  [ -f "${DEVBOOST_SYSTEMD_SYSTEM_DIR}/nvidia-resign.service" ]
  grep -q 'Type=oneshot' "${DEVBOOST_SYSTEMD_SYSTEM_DIR}/nvidia-resign.service"
  grep -q 'Before=display-manager.service' "${DEVBOOST_SYSTEMD_SYSTEM_DIR}/nvidia-resign.service"
  grep -q 'enable nvidia-resign.service' "${STUB_SYSTEMCTL_LOG}"
}

@test "nvidia-resign-service: idempotent (second run still GREEN)" {
  _run_install nvidia-resign-service
  run _run_install nvidia-resign-service
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_SBIN_DIR}/sign-nvidia-modules" ]
}

@test "nvidia-resign-service: verify GREEN when script + unit present" {
  _run_install nvidia-resign-service
  run bash -c "
    export DEVBOOST_SBIN_DIR='${DEVBOOST_SBIN_DIR}'
    export DEVBOOST_SYSTEMD_SYSTEM_DIR='${DEVBOOST_SYSTEMD_SYSTEM_DIR}'
    bash '${DEVBOOST_ROOT}/modules/nvidia-resign-service/verify.sh'
  "
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# cuda / libva-nvidia-driver / nvidia-container-toolkit (FR-006, FR-010)
# ---------------------------------------------------------------------------

@test "cuda: dnf installs xorg-x11-drv-nvidia-cuda" {
  run _run_install cuda
  [ "$status" -eq 0 ]
  grep -q 'xorg-x11-drv-nvidia-cuda' "${STUB_DNF_LOG}"
}

@test "cuda: verify uses rpm -q xorg-x11-drv-nvidia-cuda" {
  run _module_verify_cmd cuda
  [[ "$output" == *"rpm -q xorg-x11-drv-nvidia-cuda"* ]]
}

@test "libva-nvidia-driver: dnf installs libva-nvidia-driver (renamed pkg)" {
  run _run_install libva-nvidia-driver
  [ "$status" -eq 0 ]
  grep -q 'libva-nvidia-driver' "${STUB_DNF_LOG}"
}

@test "libva-nvidia-driver: verify uses rpm -q libva-nvidia-driver" {
  run _module_verify_cmd libva-nvidia-driver
  [[ "$output" == *"rpm -q libva-nvidia-driver"* ]]
}

@test "nvidia-container-toolkit: dnf install + nvidia-ctk runtime configure" {
  run _run_install nvidia-container-toolkit
  [ "$status" -eq 0 ]
  grep -q 'nvidia-container-toolkit' "${STUB_DNF_LOG}"
  grep -q 'nvidia-ctk runtime configure' "${STUB_KERNEL_LOG}"
}

@test "nvidia-container-toolkit: verify uses command -v nvidia-ctk" {
  run _module_verify_cmd nvidia-container-toolkit
  [[ "$output" == *"nvidia-ctk"* ]]
}
