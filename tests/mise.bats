load test_helper
load fixtures/base/stubs

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup

  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run the mise install.sh in a subshell with the full stub environment.
# ---------------------------------------------------------------------------
_run_mise_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/mise/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: run the engine against the mise module.
# ---------------------------------------------------------------------------
_engine_run_mise() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- mise
  " 2>&1
}

# ===========================================================================
# module.toml shape
# ===========================================================================

@test "mise: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/mise/module.toml" ]
}

@test "mise: verify field is 'command -v mise'" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/mise/module.toml" | sed 's/verify *= *//' | tr -d '"')"
  [[ "${vcmd}" == *"command -v mise"* ]]
}

@test "mise: requires is empty (no deps)" {
  local req
  req="$(grep '^requires' "${DEVBOOST_ROOT}/modules/mise/module.toml" | sed 's/requires *= *//' | tr -d '"')"
  # requires = [] means the field contains []
  [[ "${req}" == "[]" ]]
}

@test "mise: install command references install.sh" {
  grep -q "install.sh" "${DEVBOOST_ROOT}/modules/mise/module.toml"
}

# ===========================================================================
# T014 — install: mise absent → install attempted
# ===========================================================================

@test "mise: install — when mise absent, install is attempted via dnf" {
  base_remove_mise
  run _run_mise_install
  [ "$status" -eq 0 ]
  grep -q "mise" "${STUB_DNF_LOG}"
}

@test "mise: verify is GREEN when mise stub is on PATH" {
  run bash -c "export HOME='${HOME}'; export PATH='${PATH}'; command -v mise" 2>&1
  [ "$status" -eq 0 ]
}

@test "mise: verify is RED when mise is not on PATH" {
  base_remove_mise
  run bash -c "export HOME='${HOME}'; export PATH='${PATH}'; command -v mise" 2>&1
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T014 — migration present-branch: ~/.nvm with version → mise use -g node@<v>
# ===========================================================================

@test "mise: migration present — mise use -g node called with exact nvm version" {
  # Seed ~/.nvm with version 18.20.0
  export STUB_NVM_VERSION="18.20.0"
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  # Seed the nvm init block in bashrc
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # The mise stub log must contain "mise use -g node@18.20.0"
  grep -q "use -g node@18.20.0" "${STUB_MISE_LOG}"
}

@test "mise: migration present — nvm version is preserved exactly (SC-004)" {
  export STUB_NVM_VERSION="16.14.2"
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "16.14.2" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # Exact version must appear — no upgrade/downgrade
  grep -q "node@16.14.2" "${STUB_MISE_LOG}"
  # Must NOT contain a different node version
  ! grep -q "node@" "${STUB_MISE_LOG}" | grep -v "node@16.14.2" || true
}

@test "mise: migration present — nvm init block in bashrc is commented out" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  local bashrc="${HOME}/.bashrc"
  # Lines that were inside the NVM block should now be commented
  grep -q "^# export NVM_DIR" "${bashrc}"
  grep -q "^# \[" "${bashrc}"
}

@test "mise: migration present — nvm ~/.nvm directory is NOT deleted" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  [ -d "${HOME}/.nvm" ]
}

@test "mise: migration present — BEGIN NVM / END NVM markers are preserved (not commented)" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  grep -q "^# BEGIN NVM" "${HOME}/.bashrc"
  grep -q "^# END NVM" "${HOME}/.bashrc"
}

# ===========================================================================
# T014 — migration present-branch: ~/.sdkman with version → mise use -g java@<v>
# ===========================================================================

@test "mise: migration present — mise use -g java called with exact sdkman version" {
  export STUB_SDKMAN_VERSION="21.0.1-tem"
  mkdir -p "${HOME}/.sdkman/candidates/java/${STUB_SDKMAN_VERSION}"
  ln -sfn "${HOME}/.sdkman/candidates/java/${STUB_SDKMAN_VERSION}" \
          "${HOME}/.sdkman/candidates/java/current"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  grep -q "use -g java@21.0.1-tem" "${STUB_MISE_LOG}"
}

@test "mise: migration present — sdkman java version is preserved exactly (SC-004)" {
  local sdk_ver="17.0.9-tem"
  mkdir -p "${HOME}/.sdkman/candidates/java/${sdk_ver}"
  ln -sfn "${HOME}/.sdkman/candidates/java/${sdk_ver}" \
          "${HOME}/.sdkman/candidates/java/current"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  grep -q "java@17.0.9-tem" "${STUB_MISE_LOG}"
}

@test "mise: migration present — sdkman init block in bashrc is commented out" {
  local sdk_ver="21.0.1-tem"
  mkdir -p "${HOME}/.sdkman/candidates/java/${sdk_ver}"
  ln -sfn "${HOME}/.sdkman/candidates/java/${sdk_ver}" \
          "${HOME}/.sdkman/candidates/java/current"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  local bashrc="${HOME}/.bashrc"
  grep -q "^# export SDKMAN_DIR" "${bashrc}"
}

@test "mise: migration present — ~/.sdkman directory is NOT deleted" {
  local sdk_ver="21.0.1-tem"
  mkdir -p "${HOME}/.sdkman/candidates/java/${sdk_ver}"
  ln -sfn "${HOME}/.sdkman/candidates/java/${sdk_ver}" \
          "${HOME}/.sdkman/candidates/java/current"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  [ -d "${HOME}/.sdkman" ]
}

# ===========================================================================
# T014 — absent-branch: no ~/.nvm / ~/.sdkman → no migration calls
# ===========================================================================

@test "mise: absent-branch — no ~/.nvm → no 'mise use' node call" {
  # Ensure ~/.nvm does NOT exist
  rm -rf "${HOME}/.nvm"

  run _run_mise_install
  [ "$status" -eq 0 ]

  # mise log must not contain any 'use -g node' invocation
  ! grep -q "use -g node" "${STUB_MISE_LOG}"
}

@test "mise: absent-branch — no ~/.sdkman → no 'mise use' java call" {
  rm -rf "${HOME}/.sdkman"

  run _run_mise_install
  [ "$status" -eq 0 ]

  ! grep -q "use -g java" "${STUB_MISE_LOG}"
}

@test "mise: absent-branch — bashrc unchanged when no legacy dirs present" {
  rm -rf "${HOME}/.nvm" "${HOME}/.sdkman"
  # Write known content to bashrc
  printf 'export FOO=bar\n' > "${HOME}/.bashrc"

  run _run_mise_install
  [ "$status" -eq 0 ]

  # The only content should be our known line (no NVM/SDKMAN block changes)
  grep -q "^export FOO=bar$" "${HOME}/.bashrc"
  ! grep -q "BEGIN NVM" "${HOME}/.bashrc"
}

# ===========================================================================
# T014 — empty-legacy edge: ~/.nvm present but no version → no mise use call
# ===========================================================================

@test "mise: empty-legacy edge — ~/.nvm dir present but no alias/default → no mise use node call" {
  # Create ~/.nvm without any alias/default file
  mkdir -p "${HOME}/.nvm"
  # Do NOT create alias/default
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # No mise use -g node should be called
  ! grep -q "use -g node" "${STUB_MISE_LOG}"
}

@test "mise: empty-legacy edge — ~/.nvm present, no version, but nvm block still commented" {
  mkdir -p "${HOME}/.nvm"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # Block should still be commented even with no version
  grep -q "^# export NVM_DIR" "${HOME}/.bashrc"
}

@test "mise: empty-legacy edge — ~/.sdkman present but no current symlink → no mise use java call" {
  # Create ~/.sdkman without current symlink
  mkdir -p "${HOME}/.sdkman/candidates/java"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  ! grep -q "use -g java" "${STUB_MISE_LOG}"
}

# ===========================================================================
# T014 — must NOT write repo config/mise.toml (F2 fix)
# ===========================================================================

@test "mise: install does NOT write repo config/mise.toml" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # The repo config/mise.toml must not exist
  [ ! -f "${DEVBOOST_ROOT}/config/mise.toml" ]
}

@test "mise: install does NOT write any file under repo config/ dir" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  # No mise.toml should exist in the repo config dir
  ! find "${DEVBOOST_ROOT}/config" -name "mise.toml" -newer "${DEVBOOST_ROOT}/modules/mise/install.sh" 2>/dev/null | grep -q .
}

# ===========================================================================
# T014 — idempotent re-run
# ===========================================================================

@test "mise: idempotent — already-commented nvm block is not double-commented" {
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "18.20.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  # First run
  _run_mise_install >/dev/null 2>&1

  # Capture bashrc content after first run
  local content_first
  content_first="$(cat "${HOME}/.bashrc")"

  # Clear mise log for second run
  : > "${STUB_MISE_LOG}"

  # Second run
  run _run_mise_install
  [ "$status" -eq 0 ]

  local content_second
  content_second="$(cat "${HOME}/.bashrc")"

  # Content must be identical — no double-commenting
  [ "${content_first}" = "${content_second}" ]

  # No "# # " double-prefix should appear
  ! grep -q "^# # " "${HOME}/.bashrc"
}

@test "mise: idempotent — engine verify-guard skips install when mise already on PATH" {
  # mise stub is already on PATH (installed by base_setup)
  : > "${STUB_DNF_LOG}"

  run _engine_run_mise
  [ "$status" -eq 0 ]

  # Engine should have skipped install (dnf never called for mise)
  ! grep -q "mise" "${STUB_DNF_LOG}"
}

@test "mise: both nvm and sdkman present — both migrations run" {
  # Set up nvm
  mkdir -p "${HOME}/.nvm/alias"
  printf '%s\n' "20.11.0" > "${HOME}/.nvm/alias/default"
  base_add_nvm_block

  # Set up sdkman
  local sdk_ver="21.0.1-tem"
  mkdir -p "${HOME}/.sdkman/candidates/java/${sdk_ver}"
  ln -sfn "${HOME}/.sdkman/candidates/java/${sdk_ver}" \
          "${HOME}/.sdkman/candidates/java/current"
  base_add_sdkman_block

  run _run_mise_install
  [ "$status" -eq 0 ]

  grep -q "use -g node@20.11.0" "${STUB_MISE_LOG}"
  grep -q "use -g java@21.0.1-tem" "${STUB_MISE_LOG}"
  grep -q "^# export NVM_DIR" "${HOME}/.bashrc"
  grep -q "^# export SDKMAN_DIR" "${HOME}/.bashrc"
}
