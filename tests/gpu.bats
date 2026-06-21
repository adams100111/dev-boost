load test_helper
load fixtures/base/stubs

# Spec 10 (system-resilience): gpu-detect module + lib/gpu.sh gpu_doctor.
# Vendor classification reuses the lspci stub (STUB_GPU_VENDOR); gpu_doctor uses
# the kernel stubs (modprobe/dmesg) + a scratch modprobe.d dir.

setup() {
  load_lib log.sh
  base_setup
  base_install_kernel_stubs
  # Scratch modprobe.d + marker so we never touch the real /etc or repo tree.
  export DEVBOOST_MODPROBE_DIR="${BATS_TEST_TMPDIR}/modprobe.d"
  export DEVBOOST_GPU_MARKER="${BATS_TEST_TMPDIR}/gpu.selected"
  mkdir -p "${DEVBOOST_MODPROBE_DIR}"
  source "${DEVBOOST_ROOT}/lib/gpu.sh"
}

teardown() {
  base_remove_kernel_stubs
  base_teardown
}

# Run gpu-detect/install.sh in a subshell with the full stub env.
_run_gpu_detect() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_GPU_VENDOR='${STUB_GPU_VENDOR:-intel}'
    export STUB_LSPCI_LOG='${STUB_LSPCI_LOG}'
    export DEVBOOST_GPU_MARKER='${DEVBOOST_GPU_MARKER}'
    bash '${DEVBOOST_ROOT}/modules/gpu-detect/install.sh'
  " 2>&1
}

# ===========================================================================
# gpu_detect_vendor — vendor classification
# ===========================================================================

@test "gpu_detect_vendor: intel → intel" {
  export STUB_GPU_VENDOR="intel"
  run gpu_detect_vendor
  [ "$status" -eq 0 ]
  [ "$output" = "intel" ]
}

@test "gpu_detect_vendor: amd → amd" {
  export STUB_GPU_VENDOR="amd"
  run gpu_detect_vendor
  [ "$status" -eq 0 ]
  [ "$output" = "amd" ]
}

@test "gpu_detect_vendor: nvidia → nvidia" {
  export STUB_GPU_VENDOR="nvidia"
  run gpu_detect_vendor
  [ "$status" -eq 0 ]
  [ "$output" = "nvidia" ]
}

@test "gpu_detect_vendor: hybrid intel+nvidia → both vendors" {
  export STUB_GPU_VENDOR="intel+nvidia"
  run gpu_detect_vendor
  [ "$status" -eq 0 ]
  [[ "$output" == *intel* ]]
  [[ "$output" == *nvidia* ]]
}

@test "gpu_detect_vendor: unknown vendor → not classified, surfaced via GPU_UNRECOGNIZED" {
  export STUB_GPU_VENDOR="unknown"
  gpu_detect_vendor >/dev/null
  [ -z "${GPU_UNRECOGNIZED// /}" ] && false || true
  [[ "${GPU_UNRECOGNIZED}" == *XYZ* ]]
}

# ===========================================================================
# gpu-detect module — marker selection
# ===========================================================================

@test "gpu-detect: nvidia present → marker selects nvidia" {
  export STUB_GPU_VENDOR="nvidia"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [ "$(cat "${DEVBOOST_GPU_MARKER}")" = "nvidia" ]
}

@test "gpu-detect: intel → marker selects open" {
  export STUB_GPU_VENDOR="intel"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [ "$(cat "${DEVBOOST_GPU_MARKER}")" = "open" ]
}

@test "gpu-detect: amd → marker selects open" {
  export STUB_GPU_VENDOR="amd"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [ "$(cat "${DEVBOOST_GPU_MARKER}")" = "open" ]
}

@test "gpu-detect: hybrid intel+nvidia → marker selects nvidia" {
  export STUB_GPU_VENDOR="intel+nvidia"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [ "$(cat "${DEVBOOST_GPU_MARKER}")" = "nvidia" ]
}

@test "gpu-detect: nvidia present → recommends hardware-nvidia profile" {
  export STUB_GPU_VENDOR="nvidia"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [[ "$output" == *hardware-nvidia* ]]
}

@test "gpu-detect: unknown vendor → reported (warn) but still records open" {
  export STUB_GPU_VENDOR="intel+unknown"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  [[ "$output" == *unrecognized* ]]
  [ "$(cat "${DEVBOOST_GPU_MARKER}")" = "open" ]
}

@test "gpu-detect: verify GREEN once marker recorded" {
  export STUB_GPU_VENDOR="intel"
  run _run_gpu_detect
  [ "$status" -eq 0 ]
  run bash -c "DEVBOOST_ROOT='${DEVBOOST_ROOT}' DEVBOOST_GPU_MARKER='${DEVBOOST_GPU_MARKER}' bash '${DEVBOOST_ROOT}/modules/gpu-detect/verify.sh'"
  [ "$status" -eq 0 ]
}

@test "gpu-detect: verify RED when no marker recorded" {
  export DEVBOOST_GPU_MARKER="${BATS_TEST_TMPDIR}/absent.selected"
  run bash -c "DEVBOOST_ROOT='${DEVBOOST_ROOT}' DEVBOOST_GPU_MARKER='${DEVBOOST_GPU_MARKER}' bash '${DEVBOOST_ROOT}/modules/gpu-detect/verify.sh'"
  [ "$status" -ne 0 ]
}

# ===========================================================================
# gpu_doctor — NVIDIA-stack diagnostics
# ===========================================================================

@test "gpu_doctor: healthy stack → exit 0" {
  : > "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
  unset STUB_MODPROBE_FAIL
  export STUB_DMESG="[    0.000000] Linux version 6.0 booting normally"
  run gpu_doctor
  [ "$status" -eq 0 ]
}

@test "gpu_doctor: nouveau not blacklisted → non-zero naming nouveau" {
  rm -f "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
  unset STUB_MODPROBE_FAIL
  export STUB_DMESG="booting normally"
  run gpu_doctor
  [ "$status" -ne 0 ]
  [[ "$output" == *nouveau* ]]
}

@test "gpu_doctor: modprobe fails → non-zero naming nvidia module" {
  : > "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
  export STUB_MODPROBE_FAIL=1
  export STUB_DMESG="booting normally"
  run gpu_doctor
  [ "$status" -ne 0 ]
  [[ "$output" == *nvidia* ]]
}

@test "gpu_doctor: dmesg reports lockdown/PKCS#7 taint → non-zero" {
  : > "${DEVBOOST_MODPROBE_DIR}/blacklist-nouveau.conf"
  unset STUB_MODPROBE_FAIL
  export STUB_DMESG="[   1.234567] Loading of unsigned module rejected: PKCS#7 signature not present; lockdown"
  run gpu_doctor
  [ "$status" -ne 0 ]
  [[ "$output" == *PKCS#7* || "$output" == *taint* || "$output" == *lockdown* ]]
}
