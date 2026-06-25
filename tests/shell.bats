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
  # ghostty is Fedora/COPR-only; other OS should fail, not silently succeed.
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
