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
# Helper: run openh264/install.sh in a subshell with full stub environment.
# ---------------------------------------------------------------------------
_run_module_oh264() {
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
    export STUB_REPO_ENABLED='${STUB_REPO_ENABLED:-}'
    bash '${DEVBOOST_ROOT}/modules/openh264/install.sh'
  " 2>&1
}

_run_verify_oh264() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    ${vcmd}
  " 2>&1
}

# ===========================================================================
# openh264 install tests
# ===========================================================================

@test "openh264: install enables fedora-cisco-openh264 repo via dnf config-manager" {
  run _run_module_oh264
  [ "$status" -eq 0 ]
  grep -q "config-manager.*setopt.*fedora-cisco-openh264" "${STUB_DNF_LOG}"
}

@test "openh264: install installs openh264 package" {
  run _run_module_oh264
  [ "$status" -eq 0 ]
  grep -qE 'install.* openh264( |$)' "${STUB_DNF_LOG}"
}

@test "openh264: install installs gstreamer1-plugin-openh264 package" {
  run _run_module_oh264
  [ "$status" -eq 0 ]
  grep -q "gstreamer1-plugin-openh264" "${STUB_DNF_LOG}"
}

@test "openh264: install installs mozilla-openh264 package" {
  run _run_module_oh264
  [ "$status" -eq 0 ]
  grep -q "mozilla-openh264" "${STUB_DNF_LOG}"
}

# ===========================================================================
# verify tests
# ===========================================================================

@test "openh264: verify GREEN when all three packages installed" {
  export STUB_RPM_INSTALLED="openh264 gstreamer1-plugin-openh264 mozilla-openh264"
  local vcmd='rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264 >/dev/null 2>&1'
  run _run_verify_oh264 "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "openh264: verify RED when openh264 is absent" {
  export STUB_RPM_INSTALLED="gstreamer1-plugin-openh264 mozilla-openh264"
  local vcmd='rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264 >/dev/null 2>&1'
  run _run_verify_oh264 "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "openh264: verify RED when gstreamer1-plugin-openh264 is absent" {
  export STUB_RPM_INSTALLED="openh264 mozilla-openh264"
  local vcmd='rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264 >/dev/null 2>&1'
  run _run_verify_oh264 "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "openh264: verify RED when mozilla-openh264 is absent" {
  export STUB_RPM_INSTALLED="openh264 gstreamer1-plugin-openh264"
  local vcmd='rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264 >/dev/null 2>&1'
  run _run_verify_oh264 "${vcmd}"
  [ "$status" -ne 0 ]
}

# ===========================================================================
# Idempotent — engine skips when verify already passes
# ===========================================================================

@test "openh264: idempotent — engine skips when all three packages already installed" {
  export STUB_RPM_INSTALLED="openh264 gstreamer1-plugin-openh264 mozilla-openh264"
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
    export STUB_RPM_INSTALLED='openh264 gstreamer1-plugin-openh264 mozilla-openh264'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- openh264
  " 2>&1
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# ===========================================================================
# Unsupported OS
# ===========================================================================

@test "openh264: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_INSTALLED=''
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- openh264
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
