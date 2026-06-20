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
# Helper: run the chezmoi install.sh in a subshell with the full stub env.
# ---------------------------------------------------------------------------
_run_chezmoi_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_CHEZMOI_LOG='${STUB_CHEZMOI_LOG}'
    export STUB_CHEZMOI_CLONE_FAIL='${STUB_CHEZMOI_CLONE_FAIL:-0}'
    bash '${DEVBOOST_ROOT}/modules/chezmoi/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: run the engine against the chezmoi module.
# ---------------------------------------------------------------------------
_engine_run_chezmoi() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_CHEZMOI_LOG='${STUB_CHEZMOI_LOG}'
    export STUB_CHEZMOI_CLONE_FAIL='${STUB_CHEZMOI_CLONE_FAIL:-0}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- chezmoi
  " 2>&1
}

# ===========================================================================
# module.toml shape
# ===========================================================================

@test "chezmoi: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/chezmoi/module.toml" ]
}

@test "chezmoi: requires=[\"secrets\"] (depends on secrets)" {
  local req
  req="$(grep '^requires' "${DEVBOOST_ROOT}/modules/chezmoi/module.toml")"
  [[ "${req}" == *'"secrets"'* ]]
}

@test "chezmoi: verify field contains 'command -v chezmoi'" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/chezmoi/module.toml")"
  [[ "${vcmd}" == *"command -v chezmoi"* ]]
}

@test "chezmoi: verify field checks ~/.local/share/chezmoi exists" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/chezmoi/module.toml")"
  [[ "${vcmd}" == *".local/share/chezmoi"* ]]
}

@test "chezmoi: install command references install.sh" {
  grep -q "install.sh" "${DEVBOOST_ROOT}/modules/chezmoi/module.toml"
}

# ===========================================================================
# T016 — success path: install + init + clone
# ===========================================================================

@test "chezmoi: success path — install exits 0" {
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
}

@test "chezmoi: success path — chezmoi init is called" {
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi: success path — ~/.local/share/chezmoi directory exists after install" {
  _run_chezmoi_install
  [ -d "${HOME}/.local/share/chezmoi" ]
}

@test "chezmoi: success path — chezmoi installed via need_cmd/dnf when absent" {
  # Remove chezmoi stub so need_cmd triggers install
  rm -f "$(base_stub_dir)/chezmoi"
  run _run_chezmoi_install
  # dnf must have been called to install chezmoi
  grep -q "chezmoi" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T016 — verify green after install
# ===========================================================================

@test "chezmoi: verify is GREEN when chezmoi on PATH and dir exists" {
  mkdir -p "${HOME}/.local/share/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    command -v chezmoi && [ -d \"\${HOME}/.local/share/chezmoi\" ]
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "chezmoi: verify is RED when chezmoi not on PATH" {
  rm -f "$(base_stub_dir)/chezmoi"
  mkdir -p "${HOME}/.local/share/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    command -v chezmoi && [ -d \"\${HOME}/.local/share/chezmoi\" ]
  " 2>&1
  [ "$status" -ne 0 ]
}

@test "chezmoi: verify is RED when chezmoi dir absent" {
  # chezmoi binary present but dir not yet created
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    command -v chezmoi && [ -d \"\${HOME}/.local/share/chezmoi\" ]
  " 2>&1
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T016 — clone-failure → warn + return 0 (non-blocking)
# ===========================================================================

@test "chezmoi: clone-failure — install returns 0 (non-blocking)" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
}

@test "chezmoi: clone-failure — log_warn is emitted (output contains [!])" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"[!]"* ]]
}

@test "chezmoi: clone-failure — chezmoi init was still attempted before failure" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  _run_chezmoi_install
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi: clone-failure — no credential or token in output" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  run _run_chezmoi_install
  # No credential-style token patterns should appear
  [[ "$output" != *"ghp_"* ]]
  [[ "$output" != *"token"*"@"* ]]
}

# ===========================================================================
# T016 — idempotent re-run (engine verify-guard)
# ===========================================================================

@test "chezmoi: idempotent — engine verify-guard skips install when chezmoi on PATH and dir exists" {
  # Pre-seed secrets verify state so the required 'secrets' dep is already satisfied.
  # secrets verify: git config user.email + ~/.git-credentials with @github.com line.
  # Write .gitconfig directly (git stub does not forward to real git).
  printf '[user]\n\temail = test@example.com\n' > "${HOME}/.gitconfig"
  touch "${HOME}/.git-credentials"
  chmod 600 "${HOME}/.git-credentials"
  printf 'https://user:token@github.com\n' > "${HOME}/.git-credentials"

  # Create chezmoi dir to satisfy the chezmoi verify command
  mkdir -p "${HOME}/.local/share/chezmoi"
  : > "${STUB_DNF_LOG}"

  run _engine_run_chezmoi
  [ "$status" -eq 0 ]

  # Engine should emit "already installed" for chezmoi and not call dnf for it
  [[ "$output" == *"already installed"* ]]
  ! grep -q "chezmoi" "${STUB_DNF_LOG}"
}

@test "chezmoi: idempotent direct re-run — second install exits 0" {
  # First run
  _run_chezmoi_install >/dev/null 2>&1
  # Second run
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
}
