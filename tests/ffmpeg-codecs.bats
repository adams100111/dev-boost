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
# Helper: run an install.sh in a subshell with the full stub environment.
# ---------------------------------------------------------------------------
_run_module() {
  local module_name="$1"
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
    bash '${DEVBOOST_ROOT}/modules/${module_name}/install.sh'
  " 2>&1
}

_run_verify() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    ${vcmd}
  " 2>&1
}

# ===========================================================================
# ffmpeg-full module tests
# ===========================================================================

@test "ffmpeg-full: install attempts dnf swap ffmpeg-free ffmpeg" {
  run _run_module ffmpeg-full
  [ "$status" -eq 0 ]
  grep -q "swap ffmpeg-free ffmpeg" "${STUB_DNF_LOG}"
}

@test "ffmpeg-full: verify GREEN when ffmpeg installed and ffmpeg-free absent" {
  export STUB_RPM_INSTALLED="ffmpeg"
  local vcmd='rpm -q ffmpeg >/dev/null 2>&1 && ! rpm -q ffmpeg-free >/dev/null 2>&1'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "ffmpeg-full: verify RED when ffmpeg-free still present (swap not done)" {
  export STUB_RPM_INSTALLED="ffmpeg ffmpeg-free"
  local vcmd='rpm -q ffmpeg >/dev/null 2>&1 && ! rpm -q ffmpeg-free >/dev/null 2>&1'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "ffmpeg-full: verify RED when ffmpeg absent" {
  export STUB_RPM_INSTALLED=""
  local vcmd='rpm -q ffmpeg >/dev/null 2>&1 && ! rpm -q ffmpeg-free >/dev/null 2>&1'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "ffmpeg-full: idempotent — engine skips when verify already passes" {
  # Also include rpmfusion packages so its verify passes (rpmfusion is a dep of ffmpeg-full).
  export STUB_RPM_INSTALLED="rpmfusion-free-release rpmfusion-nonfree-release ffmpeg"
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
    export STUB_RPM_INSTALLED='rpmfusion-free-release rpmfusion-nonfree-release ffmpeg'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- ffmpeg-full
  " 2>&1
  [ "$status" -eq 0 ]
  # install must NOT have run (verify guard fired, dnf log stays empty)
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "ffmpeg-full: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_INSTALLED=''
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- ffmpeg-full
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# codecs module tests
# ===========================================================================

@test "codecs: install attempts dnf update @multimedia" {
  run _run_module codecs
  [ "$status" -eq 0 ]
  grep -q "update @multimedia" "${STUB_DNF_LOG}"
}

@test "codecs: install passes --setopt=install_weak_deps=False" {
  run _run_module codecs
  [ "$status" -eq 0 ]
  grep -q "install_weak_deps=False" "${STUB_DNF_LOG}"
}

@test "codecs: install excludes PackageKit-gstreamer-plugin" {
  run _run_module codecs
  [ "$status" -eq 0 ]
  grep -q "PackageKit-gstreamer-plugin" "${STUB_DNF_LOG}"
}

@test "codecs: verify GREEN when representative codec package installed" {
  export STUB_RPM_INSTALLED="gstreamer1-plugins-bad-freeworld"
  local vcmd='rpm -q gstreamer1-plugins-bad-freeworld >/dev/null 2>&1'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "codecs: verify RED when representative codec package absent" {
  export STUB_RPM_INSTALLED=""
  local vcmd='rpm -q gstreamer1-plugins-bad-freeworld >/dev/null 2>&1'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "codecs: idempotent — engine skips when verify already passes" {
  # Also include rpmfusion packages so its verify passes (rpmfusion is a dep of codecs).
  export STUB_RPM_INSTALLED="rpmfusion-free-release rpmfusion-nonfree-release gstreamer1-plugins-bad-freeworld"
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
    export STUB_RPM_INSTALLED='rpmfusion-free-release rpmfusion-nonfree-release gstreamer1-plugins-bad-freeworld'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- codecs
  " 2>&1
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "codecs: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_INSTALLED=''
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- codecs
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
