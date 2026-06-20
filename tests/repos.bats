load test_helper
load fixtures/base/stubs

# DEVBOOST_ROOT is set by test_helper; expose it for subshells.

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup

  # Point DEVBOOST_MODULES_DIR at the real modules dir (modules under repo root).
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"

  # Scratch dnf.conf path (so dnf-tune never touches /etc/dnf/dnf.conf).
  export DEVBOOST_DNF_CONF="$(base_scratch_dnf_conf)"
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
    export STUB_FLATPAK_LOG='${STUB_FLATPAK_LOG}'
    export STUB_FTP_LOG='${STUB_FTP_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    export STUB_FLATPAK_REMOTES='${STUB_FLATPAK_REMOTES:-}'
    export STUB_FTP_ENABLED='${STUB_FTP_ENABLED:-0}'
    export DEVBOOST_DNF_CONF='${DEVBOOST_DNF_CONF}'
    bash '${DEVBOOST_ROOT}/modules/${module_name}/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: evaluate a verify command in a subshell with the stub env.
# ---------------------------------------------------------------------------
_run_verify() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    export STUB_FLATPAK_REMOTES='${STUB_FLATPAK_REMOTES:-}'
    export STUB_FTP_ENABLED='${STUB_FTP_ENABLED:-0}'
    export DEVBOOST_DNF_CONF='${DEVBOOST_DNF_CONF}'
    ${vcmd}
  " 2>&1
}

# ===========================================================================
# T006 / rpmfusion
# ===========================================================================

@test "rpmfusion: install attempts both release RPMs via URL" {
  run _run_module rpmfusion
  [ "$status" -eq 0 ]
  # Both free and nonfree release URLs must appear in the dnf log.
  grep -q "rpmfusion-free-release-44.noarch.rpm" "${STUB_DNF_LOG}"
  grep -q "rpmfusion-nonfree-release-44.noarch.rpm" "${STUB_DNF_LOG}"
}

@test "rpmfusion: install runs dnf upgrade --refresh" {
  run _run_module rpmfusion
  [ "$status" -eq 0 ]
  grep -q "upgrade --refresh" "${STUB_DNF_LOG}"
}

@test "rpmfusion: install runs dnf install appstream-data" {
  run _run_module rpmfusion
  [ "$status" -eq 0 ]
  grep -q "appstream-data" "${STUB_DNF_LOG}"
}

@test "rpmfusion: verify is GREEN after install (both rpms reported installed)" {
  # Simulate both packages installed.
  export STUB_RPM_INSTALLED="rpmfusion-free-release rpmfusion-nonfree-release"
  local vcmd='rpm -q rpmfusion-free-release rpmfusion-nonfree-release'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "rpmfusion: verify is RED before install (packages absent)" {
  export STUB_RPM_INSTALLED=""
  local vcmd='rpm -q rpmfusion-free-release rpmfusion-nonfree-release'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "rpmfusion: module.toml verify command checks both release packages" {
  # Confirm the TOML verify field references both packages.
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/rpmfusion/module.toml" | sed "s/verify *= *//" | tr -d '"')"
  [[ "${vcmd}" == *"rpmfusion-free-release"* ]]
  [[ "${vcmd}" == *"rpmfusion-nonfree-release"* ]]
}

@test "rpmfusion: idempotent — engine skips when verify already passes" {
  export STUB_RPM_INSTALLED="rpmfusion-free-release rpmfusion-nonfree-release"
  # Clear the log first.
  : > "${STUB_DNF_LOG}"
  # Run the engine against the module with verify green; install cmd must NOT run.
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
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- rpmfusion
  "
  [ "$status" -eq 0 ]
  # dnf log should remain empty (verify guard fired, install not called).
  [ ! -s "${STUB_DNF_LOG}" ]
}

# ===========================================================================
# T006 / dnf-tune
# ===========================================================================

@test "dnf-tune: install writes max_parallel_downloads=10 into dnf.conf" {
  run _run_module dnf-tune
  [ "$status" -eq 0 ]
  grep -q "^max_parallel_downloads=10$" "${DEVBOOST_DNF_CONF}"
}

@test "dnf-tune: install writes fastestmirror=true into dnf.conf" {
  run _run_module dnf-tune
  [ "$status" -eq 0 ]
  grep -q "^fastestmirror=true$" "${DEVBOOST_DNF_CONF}"
}

@test "dnf-tune: idempotent — re-run does NOT duplicate max_parallel_downloads" {
  _run_module dnf-tune
  _run_module dnf-tune
  local count
  count="$(grep -c "^max_parallel_downloads=" "${DEVBOOST_DNF_CONF}")"
  [ "${count}" -eq 1 ]
}

@test "dnf-tune: idempotent — re-run does NOT duplicate fastestmirror" {
  _run_module dnf-tune
  _run_module dnf-tune
  local count
  count="$(grep -c "^fastestmirror=" "${DEVBOOST_DNF_CONF}")"
  [ "${count}" -eq 1 ]
}

@test "dnf-tune: reconciles pre-existing max_parallel_downloads with wrong value" {
  printf 'max_parallel_downloads=3\n' > "${DEVBOOST_DNF_CONF}"
  _run_module dnf-tune
  grep -q "^max_parallel_downloads=10$" "${DEVBOOST_DNF_CONF}"
  # Still only one line.
  [ "$(grep -c "^max_parallel_downloads=" "${DEVBOOST_DNF_CONF}")" -eq 1 ]
}

@test "dnf-tune: reconciles pre-existing fastestmirror with wrong value" {
  printf 'fastestmirror=false\n' > "${DEVBOOST_DNF_CONF}"
  _run_module dnf-tune
  grep -q "^fastestmirror=true$" "${DEVBOOST_DNF_CONF}"
  [ "$(grep -c "^fastestmirror=" "${DEVBOOST_DNF_CONF}")" -eq 1 ]
}

@test "dnf-tune: verify is GREEN when both keys are present" {
  printf 'max_parallel_downloads=10\nfastestmirror=true\n' > "${DEVBOOST_DNF_CONF}"
  local vcmd='grep -q "^max_parallel_downloads=10$" "${DEVBOOST_DNF_CONF}" && grep -q "^fastestmirror=true$" "${DEVBOOST_DNF_CONF}"'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "dnf-tune: verify is RED when dnf.conf is missing a key" {
  printf 'max_parallel_downloads=10\n' > "${DEVBOOST_DNF_CONF}"
  local vcmd='grep -q "^max_parallel_downloads=10$" "${DEVBOOST_DNF_CONF}" && grep -q "^fastestmirror=true$" "${DEVBOOST_DNF_CONF}"'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T006 / fedora-third-party
# ===========================================================================

@test "fedora-third-party: install calls fedora-third-party enable" {
  run _run_module fedora-third-party
  [ "$status" -eq 0 ]
  grep -q "fedora-third-party enable" "${STUB_FTP_LOG}"
}

@test "fedora-third-party: verify is GREEN when query reports enabled" {
  export STUB_FTP_ENABLED="1"
  local vcmd='fedora-third-party query | grep -q enabled'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "fedora-third-party: verify is RED when query reports disabled" {
  export STUB_FTP_ENABLED="0"
  local vcmd='fedora-third-party query | grep -q enabled'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "fedora-third-party: idempotent — engine skips when already enabled" {
  export STUB_FTP_ENABLED="1"
  : > "${STUB_FTP_LOG}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_FTP_LOG='${STUB_FTP_LOG}'
    export STUB_FTP_ENABLED='1'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- fedora-third-party
  "
  [ "$status" -eq 0 ]
  # 'enable' must NOT appear in the log (engine guard fired).
  ! grep -q "enable" "${STUB_FTP_LOG}"
}

# ===========================================================================
# T006 / flatpak
# ===========================================================================

@test "flatpak: install adds flathub remote when not present" {
  export STUB_FLATPAK_REMOTES=""
  run _run_module flatpak
  [ "$status" -eq 0 ]
  grep -q "remote-add" "${STUB_FLATPAK_LOG}"
  grep -q "flathub" "${STUB_FLATPAK_LOG}"
}

@test "flatpak: install does NOT re-add flathub when already present" {
  export STUB_FLATPAK_REMOTES="flathub"
  run _run_module flatpak
  [ "$status" -eq 0 ]
  # remote-add must NOT appear (skip path taken).
  ! grep -q "remote-add" "${STUB_FLATPAK_LOG}"
}

@test "flatpak: install runs remote-modify --no-filter to unfilter flathub" {
  export STUB_FLATPAK_REMOTES=""
  run _run_module flatpak
  [ "$status" -eq 0 ]
  grep -q "remote-modify" "${STUB_FLATPAK_LOG}"
  grep -q "\-\-no-filter" "${STUB_FLATPAK_LOG}"
}

@test "flatpak: verify is GREEN when flathub is in STUB_FLATPAK_REMOTES" {
  export STUB_FLATPAK_REMOTES="flathub"
  local vcmd='flatpak remotes | awk '"'"'{print $1}'"'"' | grep -qxF flathub'
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "flatpak: verify is RED when flathub is absent" {
  export STUB_FLATPAK_REMOTES=""
  local vcmd='flatpak remotes | awk '"'"'{print $1}'"'"' | grep -qxF flathub'
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "flatpak: idempotent — engine skips when verify already passes" {
  export STUB_FLATPAK_REMOTES="flathub"
  : > "${STUB_FLATPAK_LOG}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_FLATPAK_LOG='${STUB_FLATPAK_LOG}'
    export STUB_FLATPAK_REMOTES='flathub'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- flatpak
  "
  [ "$status" -eq 0 ]
  # remote-add must NOT appear (engine skipped install entirely).
  ! grep -q "remote-add" "${STUB_FLATPAK_LOG}"
}

# ===========================================================================
# T006 / unsupported-OS
# ===========================================================================

@test "unsupported-OS: engine reports unsupported when OS has no fedora install key" {
  # Use a dummy module with only a fedora-specific install key; run on non-fedora OS.
  local d
  d="$(mktemp -d)"
  mkdir -p "${d}/modules/os-test"
  cat > "${d}/modules/os-test/module.toml" <<'EOF'
name = "os-test"
category = "base"
requires = []
verify = "false"

[install]
fedora = "true"
EOF
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${d}/modules'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- os-test
  "
  rm -rf "${d}"
  # Engine must report failure (unsupported), not skip.
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
