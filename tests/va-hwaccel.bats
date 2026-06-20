load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run va-hwaccel/install.sh in a subshell with full stub env.
# Use DEVBOOST_INSTALL_FLAGS="--force" (via the caller) to bypass the engine
# verify guard and reach the install script even when vainfo is stubbed OK.
# ---------------------------------------------------------------------------
_run_module_va() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    export STUB_GPU_VENDOR='${STUB_GPU_VENDOR:-intel}'
    export STUB_VAINFO_OK='${STUB_VAINFO_OK:-1}'
    export STUB_VAINFO_LOG='${STUB_VAINFO_LOG}'
    export STUB_LSPCI_LOG='${STUB_LSPCI_LOG}'
    bash '${DEVBOOST_ROOT}/modules/va-hwaccel/install.sh'
  " 2>&1
}

_run_verify_va() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_VAINFO_OK='${STUB_VAINFO_OK:-1}'
    export STUB_VAINFO_LOG='${STUB_VAINFO_LOG}'
    ${vcmd}
  " 2>&1
}

# ===========================================================================
# Intel GPU tests
# ===========================================================================

@test "va-hwaccel: Intel — installs intel-media-driver" {
  export STUB_GPU_VENDOR="intel"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "intel-media-driver" "${STUB_DNF_LOG}"
}

@test "va-hwaccel: Intel — installs libva-utils" {
  export STUB_GPU_VENDOR="intel"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "libva-utils" "${STUB_DNF_LOG}"
}

@test "va-hwaccel: Intel — verify GREEN when vainfo works" {
  export STUB_VAINFO_OK="1"
  local vcmd='vainfo >/dev/null 2>&1'
  run _run_verify_va "${vcmd}"
  [ "$status" -eq 0 ]
}

# ===========================================================================
# AMD GPU tests
# ===========================================================================

@test "va-hwaccel: AMD — swaps mesa-va-drivers to freeworld" {
  export STUB_GPU_VENDOR="amd"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "swap.*mesa-va-drivers.*mesa-va-drivers-freeworld" "${STUB_DNF_LOG}"
}

@test "va-hwaccel: AMD — swaps mesa-vdpau-drivers to freeworld" {
  export STUB_GPU_VENDOR="amd"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "swap.*mesa-vdpau-drivers.*mesa-vdpau-drivers-freeworld" "${STUB_DNF_LOG}"
}

# ===========================================================================
# NVIDIA GPU tests
# ===========================================================================

@test "va-hwaccel: NVIDIA — installs libva-nvidia-driver" {
  export STUB_GPU_VENDOR="nvidia"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "libva-nvidia-driver" "${STUB_DNF_LOG}"
}

# ===========================================================================
# Hybrid (intel+nvidia) GPU tests
# ===========================================================================

@test "va-hwaccel: Hybrid intel+nvidia — installs BOTH intel-media-driver AND libva-nvidia-driver" {
  export STUB_GPU_VENDOR="intel+nvidia"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -eq 0 ]
  grep -q "intel-media-driver" "${STUB_DNF_LOG}"
  grep -q "libva-nvidia-driver" "${STUB_DNF_LOG}"
}

# ===========================================================================
# Unrecognized vendor — must fail naming the vendor (FR-009)
# ===========================================================================

@test "va-hwaccel: unrecognized vendor — module fails naming the unmatched vendor" {
  export STUB_GPU_VENDOR="unknown"
  export STUB_VAINFO_OK="1"
  run _run_module_va
  [ "$status" -ne 0 ]
  # Output must name the unmatched vendor string
  [[ "$output" == *"XYZ"* ]] || [[ "$output" == *"unrecognized"* ]] || [[ "$output" == *"unknown"* ]]
}

# ===========================================================================
# vainfo fails after install — named failure (FR-004, no silent success)
# ===========================================================================

@test "va-hwaccel: vainfo fails after install — module fails naming GPU/driver" {
  export STUB_GPU_VENDOR="intel"
  export STUB_VAINFO_OK="0"
  run _run_module_va
  [ "$status" -ne 0 ]
  # Output must mention the failure context (GPU or driver)
  [[ "$output" == *"vainfo"* ]] || [[ "$output" == *"intel"* ]] || [[ "$output" == *"VA-API"* ]]
}

@test "va-hwaccel: vainfo fails after AMD install — module fails naming GPU/driver" {
  export STUB_GPU_VENDOR="amd"
  export STUB_VAINFO_OK="0"
  run _run_module_va
  [ "$status" -ne 0 ]
  [[ "$output" == *"vainfo"* ]] || [[ "$output" == *"amd"* ]] || [[ "$output" == *"VA-API"* ]]
}

# ===========================================================================
# Verify (top-level): vainfo exit 0 = GREEN
# ===========================================================================

@test "va-hwaccel: verify GREEN when vainfo exits 0" {
  export STUB_VAINFO_OK="1"
  local vcmd='vainfo >/dev/null 2>&1'
  run _run_verify_va "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "va-hwaccel: verify RED when vainfo exits non-zero" {
  export STUB_VAINFO_OK="0"
  local vcmd='vainfo >/dev/null 2>&1'
  run _run_verify_va "${vcmd}"
  [ "$status" -ne 0 ]
}

# ===========================================================================
# Idempotent — engine skips when verify already passes
# ===========================================================================

@test "va-hwaccel: idempotent — engine skips when vainfo already works" {
  # Include rpmfusion packages so rpmfusion verify passes (rpmfusion is a dep of va-hwaccel).
  export STUB_RPM_INSTALLED="rpmfusion-free-release rpmfusion-nonfree-release"
  export STUB_VAINFO_OK="1"
  : > "${STUB_DNF_LOG}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_INSTALLED='rpmfusion-free-release rpmfusion-nonfree-release'
    export STUB_VAINFO_OK='1'
    export STUB_VAINFO_LOG='${STUB_VAINFO_LOG}'
    export STUB_GPU_VENDOR='intel'
    export STUB_LSPCI_LOG='${STUB_LSPCI_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- va-hwaccel
  " 2>&1
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# ===========================================================================
# Unsupported OS
# ===========================================================================

@test "va-hwaccel: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_VAINFO_OK='0'
    export STUB_VAINFO_LOG='${STUB_VAINFO_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- va-hwaccel
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
