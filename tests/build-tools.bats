load test_helper
load fixtures/base/stubs

# DEVBOOST_ROOT is set by test_helper; expose it for subshells.

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run the engine install loop against a module using stub env.
# ---------------------------------------------------------------------------
_engine_install() {
  local module_name="$1"
  local distro="${2:-fedora}"
  local family="${3:-fedora}"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: resolve the install command from a module's TOML.
# ---------------------------------------------------------------------------
_module_install_cmd() {
  local module_name="$1" distro="${2:-fedora}" family="${3:-fedora}"
  bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_install_cmd '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: resolve the verify command from a module's TOML.
# ---------------------------------------------------------------------------
_module_verify_cmd() {
  local module_name="$1"
  bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_verify_cmd '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: evaluate a verify command in a subshell with stub env.
# ---------------------------------------------------------------------------
_run_verify() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    ${vcmd}
  " 2>&1
}

# ===========================================================================
# T013 — build-tools module resolves
# ===========================================================================

@test "build-tools: module file exists at modules/build-tools/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/build-tools/module.toml" ]
}

@test "build-tools: fedora install command resolves (non-empty)" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ -n "${cmd}" ]]
}

# ===========================================================================
# T013 — build-tools: exact §10c package list in fedora install command
# ===========================================================================

@test "build-tools: fedora install command contains 'make'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"make"* ]]
}

@test "build-tools: fedora install command contains 'automake'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"automake"* ]]
}

@test "build-tools: fedora install command contains 'gcc'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"gcc"* ]]
}

@test "build-tools: fedora install command contains 'gcc-c++'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"gcc-c++"* ]]
}

@test "build-tools: fedora install command contains 'kernel-devel'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"kernel-devel"* ]]
}

@test "build-tools: fedora install command contains 'cmake'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"cmake"* ]]
}

@test "build-tools: fedora install command contains 'perl'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"perl"* ]]
}

@test "build-tools: fedora install command contains 'vim'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"vim"* ]]
}

@test "build-tools: fedora install command contains 'nano'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"nano"* ]]
}

@test "build-tools: fedora install command contains 'gnupg'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"gnupg"* ]]
}

@test "build-tools: fedora install command contains 'fastfetch'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"fastfetch"* ]]
}

@test "build-tools: fedora install command contains 'unrar'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"unrar"* ]]
}

@test "build-tools: fedora install command contains 'android-tools'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"android-tools"* ]]
}

@test "build-tools: fedora install command contains 'fuse-libs'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"fuse-libs"* ]]
}

@test "build-tools: fedora install command contains 'ripgrep'" {
  local cmd
  cmd="$(_module_install_cmd build-tools fedora fedora)"
  [[ "${cmd}" == *"ripgrep"* ]]
}

# ===========================================================================
# T013 — build-tools: verify checks key compilers
# ===========================================================================

@test "build-tools: verify command checks gcc" {
  local vcmd
  vcmd="$(_module_verify_cmd build-tools)"
  [[ "${vcmd}" == *"command -v gcc"* ]]
}

@test "build-tools: verify command checks make" {
  local vcmd
  vcmd="$(_module_verify_cmd build-tools)"
  [[ "${vcmd}" == *"command -v make"* ]]
}

@test "build-tools: verify command checks cmake" {
  local vcmd
  vcmd="$(_module_verify_cmd build-tools)"
  [[ "${vcmd}" == *"command -v cmake"* ]]
}

@test "build-tools: verify is GREEN when gcc, make, cmake are all present" {
  for bin in gcc make cmake; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/${bin}"
    chmod +x "$(base_stub_dir)/${bin}"
  done
  local vcmd
  vcmd="$(_module_verify_cmd build-tools)"
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "build-tools: verify is RED when any key compiler is absent" {
  # Provide gcc and make but NOT cmake.
  for bin in gcc make; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/${bin}"
    chmod +x "$(base_stub_dir)/${bin}"
  done
  rm -f "$(base_stub_dir)/cmake"
  local vcmd
  vcmd="$(_module_verify_cmd build-tools)"
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "build-tools: idempotent — engine skips when gcc, make, cmake are present" {
  for bin in gcc make cmake; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/${bin}"
    chmod +x "$(base_stub_dir)/${bin}"
  done
  : > "${STUB_DNF_LOG}"
  run _engine_install build-tools fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "build-tools: engine calls dnf when compilers are absent (install step reached)" {
  # Remove any stubs for key compilers so the verify fails and install runs.
  rm -f "$(base_stub_dir)/gcc" "$(base_stub_dir)/make" "$(base_stub_dir)/cmake"
  : > "${STUB_DNF_LOG}"
  # Engine may exit non-zero because post-install verify fails in stub env (expected).
  _engine_install build-tools fedora fedora || true
  grep -q "dnf install" "${STUB_DNF_LOG}"
}
