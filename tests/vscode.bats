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
  # Point the repo-file write at a scratch dir so no root is needed.
  export DEVBOOST_YUM_REPOS_DIR
  DEVBOOST_YUM_REPOS_DIR="$(base_scratch_yum_repos_dir)"
}

teardown() {
  base_teardown
}

# Run vscode/install.sh in a subshell with the full stub environment.
_run_module_vscode() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export DEVBOOST_YUM_REPOS_DIR='${DEVBOOST_YUM_REPOS_DIR}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_CODE_LOG='${STUB_CODE_LOG}'
    export STUB_CODE_EXT_STATE='${STUB_CODE_EXT_STATE}'
    export STUB_CODE_EXTENSIONS='${STUB_CODE_EXTENSIONS:-}'
    bash '${DEVBOOST_ROOT}/modules/vscode/install.sh'
  " 2>&1
}

_run_verify_vscode() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_CODE_LOG='${STUB_CODE_LOG}'
    export STUB_CODE_EXT_STATE='${STUB_CODE_EXT_STATE}'
    export STUB_CODE_EXTENSIONS='${STUB_CODE_EXTENSIONS:-}'
    bash '${DEVBOOST_ROOT}/modules/vscode/verify.sh'
  " 2>&1
}

_repo_file() { printf '%s/vscode.repo\n' "${DEVBOOST_YUM_REPOS_DIR}"; }

# ===========================================================================
# Install: MS repo + code + extensions
# ===========================================================================

@test "vscode: writes the Microsoft vscode.repo" {
  run _run_module_vscode
  [ "$status" -eq 0 ]
  [ -f "$(_repo_file)" ]
  grep -q '^\[code\]' "$(_repo_file)"
  grep -q 'packages.microsoft.com/yumrepos/vscode' "$(_repo_file)"
}

@test "vscode: imports the Microsoft key and installs the code package" {
  run _run_module_vscode
  [ "$status" -eq 0 ]
  grep -q 'rpm --import' "${STUB_RPM_LOG}"
  grep -q 'install -y code' "${STUB_DNF_LOG}"
}

@test "vscode: installs every curated baseline extension on a fresh host" {
  export STUB_CODE_EXTENSIONS=""
  run _run_module_vscode
  [ "$status" -eq 0 ]
  # Each non-comment line of extensions.txt must have been installed.
  while IFS= read -r ext; do
    [[ -z "${ext}" || "${ext}" == \#* ]] && continue
    grep -q -- "--install-extension ${ext}" "${STUB_CODE_LOG}"
  done < "${DEVBOOST_ROOT}/modules/vscode/extensions.txt"
}

@test "vscode: installs ONLY the missing extensions (present ones untouched)" {
  # Pre-seed two extensions as already installed.
  export STUB_CODE_EXTENSIONS="editorconfig.editorconfig eamodio.gitlens"
  run _run_module_vscode
  [ "$status" -eq 0 ]
  # Present ones are NOT reinstalled.
  ! grep -q -- "--install-extension editorconfig.editorconfig" "${STUB_CODE_LOG}"
  ! grep -q -- "--install-extension eamodio.gitlens" "${STUB_CODE_LOG}"
  # A missing one IS installed.
  grep -q -- "--install-extension esbenp.prettier-vscode" "${STUB_CODE_LOG}"
}

# ===========================================================================
# Verify (idempotency guard)
# ===========================================================================

@test "vscode: verify GREEN after install (code present + all extensions)" {
  export STUB_CODE_EXTENSIONS=""
  _run_module_vscode >/dev/null
  run _run_verify_vscode
  [ "$status" -eq 0 ]
}

@test "vscode: verify RED when an extension is missing" {
  # Only one baseline extension present → verify must fail.
  export STUB_CODE_EXTENSIONS="editorconfig.editorconfig"
  run _run_verify_vscode
  [ "$status" -ne 0 ]
}

@test "vscode: verify RED when code is absent" {
  base_remove_code
  run _run_verify_vscode
  [ "$status" -ne 0 ]
}

# ===========================================================================
# Idempotency: repo file + engine skip
# ===========================================================================

@test "vscode: re-run does not duplicate the vscode.repo" {
  _run_module_vscode >/dev/null
  local first; first="$(wc -l < "$(_repo_file)")"
  _run_module_vscode >/dev/null
  local second; second="$(wc -l < "$(_repo_file)")"
  [ "${first}" -eq "${second}" ]
  # Exactly one [code] stanza.
  [ "$(grep -c '^\[code\]' "$(_repo_file)")" -eq 1 ]
}

@test "vscode: engine skips install when verify already satisfied (all extensions present)" {
  # Seed all baseline extensions as installed so verify is GREEN up-front.
  local all; all="$(grep -vE '^#|^$' "${DEVBOOST_ROOT}/modules/vscode/extensions.txt" | tr '\n' ' ')"
  : > "${STUB_DNF_LOG}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export DEVBOOST_YUM_REPOS_DIR='${DEVBOOST_YUM_REPOS_DIR}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_CODE_LOG='${STUB_CODE_LOG}'
    export STUB_CODE_EXT_STATE='${STUB_CODE_EXT_STATE}'
    export STUB_CODE_EXTENSIONS='${all}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- vscode
  " 2>&1
  [ "$status" -eq 0 ]
  # Verify-satisfied ⇒ no dnf install ran.
  [ ! -s "${STUB_DNF_LOG}" ]
}

# ===========================================================================
# Unsupported OS
# ===========================================================================

@test "vscode: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- vscode
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
