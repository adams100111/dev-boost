load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run an escape-hatch install.sh in a fully-stubbed subshell.
# Passes all log knobs so stubs write to the test-scoped log files.
# ---------------------------------------------------------------------------
_run_install_sh() {
  local module="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    export STUB_COPR_ENABLED='${STUB_COPR_ENABLED:-}'
    export STUB_APT_LOG='${STUB_APT_LOG:-}'
    export STUB_DPKG_ARCH='${STUB_DPKG_ARCH:-amd64}'
    export STUB_GHOSTTY_UBUNTU='${STUB_GHOSTTY_UBUNTU:-}'
    export STUB_GHOSTTY_ARCH='${STUB_GHOSTTY_ARCH:-amd64}'
    export STUB_GHOSTTY_CODENAME='${STUB_GHOSTTY_CODENAME:-24.04}'
    export STUB_CURL_LOG='${STUB_CURL_LOG:-}'
    export OS_RELEASE_FILE='${OS_RELEASE_FILE:-/etc/os-release}'
    bash '${DEVBOOST_ROOT}/modules/${module}/install.sh'
  " 2>&1
}

# ===========================================================================
# starship
# ===========================================================================

@test "starship: module file exists at modules/starship/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/starship/module.toml" ]
}

@test "starship: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/starship/install.sh" ]
}

@test "starship: install command is the escape-hatch (runs install.sh)" {
  local cmd
  cmd="$(_module_install_cmd starship fedora fedora)"
  [[ "${cmd}" == *"modules/starship/install.sh"* ]]
}

@test "starship: verify command checks 'command -v starship'" {
  local vcmd
  vcmd="$(_module_verify_cmd starship)"
  [[ "${vcmd}" == *"command -v starship"* ]]
}

@test "starship: category is shell" {
  local toml="${DEVBOOST_ROOT}/modules/starship/module.toml"
  [ -f "${toml}" ]
  grep -q 'category.*=.*"shell"' "${toml}"
}

@test "starship: requires is empty" {
  local req
  req="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires starship
  " 2>&1)"
  [[ -z "${req}" ]]
}

@test "starship: install.sh runs dnf install for starship" {
  run _run_install_sh starship
  [ "$status" -eq 0 ]
  grep -q "dnf.*install.*starship" "${STUB_DNF_LOG}" \
    || grep -q "dnf install" "${STUB_DNF_LOG}"
}

@test "starship: install.sh does NOT edit ~/.bashrc" {
  run _run_install_sh starship
  [ "$status" -eq 0 ]
  # The actual file should not contain starship init line written by the module
  if [[ -f "${HOME}/.bashrc" ]]; then
    ! grep -q "starship init" "${HOME}/.bashrc"
  fi
}

@test "starship: engine skips when starship binary is present (idempotent)" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/starship"
  chmod +x "$(base_stub_dir)/starship"
  : > "${STUB_DNF_LOG}"
  run _engine_install starship fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "starship: install is reachable via --force (host-independent)" {
  rm -f "$(base_stub_dir)/starship"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install starship fedora fedora || true
  grep -q "dnf" "${STUB_DNF_LOG}"
}

@test "starship: default install key — engine resolves install on non-fedora OS" {
  # --force bypasses the idempotency guard so the engine actually RESOLVES and runs
  # the portable `default` install command on debian (proving it is not unsupported).
  # On debian the install.sh else-branch runs the official starship.rs script via the
  # stubbed curl|sh; seed a starship binary so the post-install verify passes, so the
  # engine reports success rather than a verify failure.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/starship"
  chmod +x "$(base_stub_dir)/starship"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install starship ubuntu debian
  [ "$status" -eq 0 ]
  # With the default key, the engine must not report unsupported on debian.
  [[ "$output" != *"unsupported"* ]]
}

# ===========================================================================
# ghostty
# ===========================================================================

@test "ghostty: module file exists at modules/ghostty/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/ghostty/module.toml" ]
}

@test "ghostty: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/ghostty/install.sh" ]
}

@test "ghostty: install command is the escape-hatch (runs install.sh)" {
  local cmd
  cmd="$(_module_install_cmd ghostty fedora fedora)"
  [[ "${cmd}" == *"modules/ghostty/install.sh"* ]]
}

@test "ghostty: verify command checks 'command -v ghostty'" {
  local vcmd
  vcmd="$(_module_verify_cmd ghostty)"
  [[ "${vcmd}" == *"command -v ghostty"* ]]
}

@test "ghostty: category is shell" {
  local toml="${DEVBOOST_ROOT}/modules/ghostty/module.toml"
  [ -f "${toml}" ]
  grep -q 'category.*=.*"shell"' "${toml}"
}

@test "ghostty: requires is empty" {
  local req
  req="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires ghostty
  " 2>&1)"
  [[ -z "${req}" ]]
}

@test "ghostty: install.sh enables scottames/ghostty COPR" {
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  grep -q "copr.*enable.*scottames/ghostty" "${STUB_DNF_LOG}" \
    || grep -q "scottames/ghostty" "${STUB_DNF_LOG}"
}

@test "ghostty: install.sh runs dnf install ghostty" {
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  grep -q "dnf.*install.*ghostty\b" "${STUB_DNF_LOG}" \
    || (grep -q "dnf" "${STUB_DNF_LOG}" && grep -q "ghostty" "${STUB_DNF_LOG}")
}

@test "ghostty: COPR NOT re-added when scottames/ghostty already enabled" {
  export STUB_COPR_ENABLED="scottames/ghostty"
  : > "${STUB_DNF_LOG}"
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  # When the COPR is already enabled, copr enable must NOT be invoked.
  ! grep -q "copr enable" "${STUB_DNF_LOG}"
  # The package install must still proceed.
  grep -q "install" "${STUB_DNF_LOG}"
}

@test "ghostty: COPR IS added when scottames/ghostty not yet enabled" {
  unset STUB_COPR_ENABLED
  : > "${STUB_DNF_LOG}"
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  # When the COPR is absent, copr enable must be invoked exactly once.
  [ "$(grep -c "copr enable" "${STUB_DNF_LOG}")" -eq 1 ]
}

@test "ghostty: engine skips when ghostty binary is present (idempotent)" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/ghostty"
  chmod +x "$(base_stub_dir)/ghostty"
  : > "${STUB_DNF_LOG}"
  run _engine_install ghostty fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "ghostty: install is reachable via --force (host-independent)" {
  rm -f "$(base_stub_dir)/ghostty"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install ghostty fedora fedora || true
  grep -q "dnf" "${STUB_DNF_LOG}"
}

@test "ghostty: unsupported OS — engine reports failure (not a skip)" {
  # ghostty supports fedora + debian; other OS families (e.g. arch) should fail.
  # Use --force to bypass the idempotency guard so we reach the icmd check
  # even when ghostty binary happens to be on the host PATH.
  rm -f "$(base_stub_dir)/ghostty"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install ghostty arch arch
  [[ "$output" == *"unsupported"* ]]
}

@test "ghostty: Ptyxis is NOT removed by install.sh" {
  # install.sh must not invoke any uninstall/remove command for ptyxis
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  ! grep -qi "ptyxis" "${STUB_DNF_LOG}" \
    || ! grep -qi "remove\|erase\|autoremove" <(grep -i "ptyxis" "${STUB_DNF_LOG}" 2>/dev/null || true)
}

@test "ghostty: debian install key resolves install.sh" {
  local cmd
  cmd="$(_module_install_cmd ghostty ubuntu debian)"
  [[ "${cmd}" == *"modules/ghostty/install.sh"* ]]
}

@test "ghostty: debian install.sh downloads and installs matching .deb (real success)" {
  # Write a fake os-release with Ubuntu codename so the asset URL matches.
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=24.04\n' > "${fake_os_release}"
  local _stub_dir; _stub_dir="$(base_stub_dir)"
  rm -f "${_stub_dir}/ghostty"
  : > "${STUB_APT_LOG}"
  # Override `command` so that `command -v ghostty` uses the stub dir (not host PATH).
  # Before apt-get installs ghostty into the stub dir, the check returns false.
  # After the apt-get stub creates ${_stub_dir}/ghostty, the check returns true.
  command() {
    if [[ "$1" == "-v" && "$2" == "ghostty" ]]; then
      local _sd; _sd="${STUB_GHOSTTY_STUB_DIR:-}"
      [[ -n "${_sd}" && -f "${_sd}/ghostty" ]] && printf '%s/ghostty\n' "${_sd}" && return 0
      return 1
    fi
    builtin command "$@"
  }
  export -f command
  export STUB_GHOSTTY_STUB_DIR="${_stub_dir}"
  local _out _status
  _out="$(bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export OS_RELEASE_FILE='${fake_os_release}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_RPM_INSTALLED=''
    export STUB_COPR_ENABLED=''
    export STUB_APT_LOG='${STUB_APT_LOG}'
    export STUB_DPKG_ARCH='amd64'
    export STUB_GHOSTTY_UBUNTU='1'
    export STUB_GHOSTTY_ARCH='amd64'
    export STUB_GHOSTTY_CODENAME='24.04'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_GHOSTTY_STUB_DIR='${_stub_dir}'
    bash '${DEVBOOST_ROOT}/modules/ghostty/install.sh'
  " 2>&1)"
  _status=$?
  # Unset the command override so remaining tests are unaffected.
  unset -f command
  unset STUB_GHOSTTY_STUB_DIR
  # The apt-get stub creates a ghostty binary in the stub dir — verify really passes.
  [ "${_status}" -eq 0 ]
  # apt-get was called with a .deb argument.
  grep -q "apt-get install" "${STUB_APT_LOG}"
  grep -q "\.deb" "${STUB_APT_LOG}"
  # The ghostty binary is now present (placed by the apt-get stub).
  [ -f "${_stub_dir}/ghostty" ]
}

@test "ghostty: debian install.sh — idempotent skip when ghostty already present" {
  # When ghostty binary is already on PATH, install.sh must skip without calling apt-get.
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=24.04\n' > "${fake_os_release}"
  # Ensure ghostty is present in the stub dir.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/ghostty"
  chmod +x "$(base_stub_dir)/ghostty"
  export OS_FAMILY=debian
  export OS_DISTRO=ubuntu
  export OS_RELEASE_FILE="${fake_os_release}"
  export STUB_GHOSTTY_UBUNTU=1
  : > "${STUB_APT_LOG}"
  run _run_install_sh ghostty
  [ "$status" -eq 0 ]
  # apt-get must NOT be invoked — ghostty was already present.
  [ ! -s "${STUB_APT_LOG}" ]
}

@test "ghostty: debian install.sh — non-blocking when no .deb matches arch/codename" {
  # When the API returns no asset for the current arch/codename, install.sh warns and exits 0.
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=someunknown\n' > "${fake_os_release}"
  rm -f "$(base_stub_dir)/ghostty"
  export OS_FAMILY=debian
  export OS_DISTRO=ubuntu
  export OS_RELEASE_FILE="${fake_os_release}"
  # STUB_GHOSTTY_UBUNTU=1 but codename is "someunknown" — no asset match.
  export STUB_GHOSTTY_UBUNTU=1
  export STUB_GHOSTTY_ARCH=amd64
  export STUB_GHOSTTY_CODENAME=24.04  # stub emits 24.04 asset; script looks for "someunknown"
  : > "${STUB_APT_LOG}"
  run _run_install_sh ghostty
  # Non-blocking: must exit 0.
  [ "$status" -eq 0 ]
  # apt-get must NOT be invoked.
  [ ! -s "${STUB_APT_LOG}" ]
}

@test "ghostty: debian engine — full engine installs and verify passes" {
  # Full engine integration: OS_FAMILY=debian, ghostty absent → install → verify passes.
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=24.04\n' > "${fake_os_release}"
  local _stub_dir; _stub_dir="$(base_stub_dir)"
  rm -f "${_stub_dir}/ghostty"
  export STUB_GHOSTTY_UBUNTU=1
  export STUB_GHOSTTY_ARCH=amd64
  export STUB_GHOSTTY_CODENAME=24.04
  export OS_RELEASE_FILE="${fake_os_release}"
  # Shadow `command -v ghostty` so it resolves against the stub dir (not the host's
  # /usr/bin/ghostty). Before apt-get installs ghostty the check returns false, so
  # neither the engine's verify-skip nor install.sh's internal skip fires; after the
  # apt-get stub creates ${_stub_dir}/ghostty the check (and engine verify) pass.
  command() {
    if [[ "$1" == "-v" && "$2" == "ghostty" ]]; then
      local _sd; _sd="${STUB_GHOSTTY_STUB_DIR:-}"
      [[ -n "${_sd}" && -f "${_sd}/ghostty" ]] && printf '%s/ghostty\n' "${_sd}" && return 0
      return 1
    fi
    builtin command "$@"
  }
  export -f command
  export STUB_GHOSTTY_STUB_DIR="${_stub_dir}"
  run _engine_install ghostty ubuntu debian
  unset -f command
  unset STUB_GHOSTTY_STUB_DIR
  [ "$status" -eq 0 ]
  [[ "$output" == *"ghostty"* ]]
  # run_install swallows per-module failures in non-strict mode, so status -eq 0 is
  # hollow on its own. Assert the apt-get stub actually created the ghostty binary in
  # the stub dir — proving the debian .deb path ran AND the verify passed (mirrors test 27).
  [ -f "${_stub_dir}/ghostty" ]
}
