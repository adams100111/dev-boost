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
# Helper: run the chezmoi-repo install.sh in a subshell with the full stub env.
# ---------------------------------------------------------------------------
_run_chezmoi_repo_install() {
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
    export DEVBOOST_DOTFILES_REPO='${DEVBOOST_DOTFILES_REPO:-}'
    bash '${DEVBOOST_ROOT}/modules/chezmoi-repo/install.sh'
  " 2>&1
}

# ===========================================================================
# module.toml shape
# ===========================================================================

@test "chezmoi-repo: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/chezmoi-repo/module.toml" ]
}

@test "chezmoi-repo: requires=[\"chezmoi\",\"secrets\"] (depends on chezmoi and secrets)" {
  local req
  req="$(grep '^requires' "${DEVBOOST_ROOT}/modules/chezmoi-repo/module.toml")"
  [[ "${req}" == *'"chezmoi"'* ]]
  [[ "${req}" == *'"secrets"'* ]]
}

@test "chezmoi-repo: verify field checks ~/.local/share/chezmoi exists" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/chezmoi-repo/module.toml")"
  [[ "${vcmd}" == *".local/share/chezmoi"* ]]
}

@test "chezmoi-repo: install command references install.sh" {
  grep -q "install.sh" "${DEVBOOST_ROOT}/modules/chezmoi-repo/module.toml"
}

# ===========================================================================
# T016 — success path: init (no repo configured)
# ===========================================================================

@test "chezmoi-repo: success path — install exits 0" {
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
}

@test "chezmoi-repo: success path — chezmoi init is called" {
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi-repo: success path — ~/.local/share/chezmoi directory exists after install" {
  _run_chezmoi_repo_install
  [ -d "${HOME}/.local/share/chezmoi" ]
}

# ===========================================================================
# T016 — DEVBOOST_DOTFILES_REPO clone path
# ===========================================================================

@test "chezmoi-repo: with DEVBOOST_DOTFILES_REPO set — init receives the repo argument" {
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  # The stub must have logged: chezmoi init --apply <repo>
  grep -q "init --apply https://github.com/testuser/dotfiles" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi-repo: with DEVBOOST_DOTFILES_REPO set — no credential or token on command line" {
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  # Output must not contain token-style strings
  [[ "$output" != *"ghp_"* ]]
  [[ "$output" != *"token"*"@"* ]]
}

@test "chezmoi-repo: without DEVBOOST_DOTFILES_REPO — local init (no repo arg) succeeds" {
  unset DEVBOOST_DOTFILES_REPO
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  # Log should contain 'chezmoi init' but NOT '--apply'
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
  ! grep -q "\-\-apply" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi-repo: without DEVBOOST_DOTFILES_REPO — output mentions no dotfiles repo configured" {
  unset DEVBOOST_DOTFILES_REPO
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"DEVBOOST_DOTFILES_REPO"* ]]
}

# ===========================================================================
# T016 — verify green/red on dir presence
# ===========================================================================

@test "chezmoi-repo: verify is GREEN when dir exists" {
  # Mirror the module's actual verify: [ -d "$HOME/.local/share/chezmoi" ]
  mkdir -p "${HOME}/.local/share/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    [ -d \"\${HOME}/.local/share/chezmoi\" ]
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "chezmoi-repo: verify is RED when dir absent" {
  # Enforce the precondition explicitly so a dir left by another test can't leak in.
  rm -rf "${HOME}/.local/share/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    [ -d \"\${HOME}/.local/share/chezmoi\" ]
  " 2>&1
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T016 — clone-failure → warn + return 0 (non-blocking)
# ===========================================================================

@test "chezmoi-repo: clone-failure — install returns 0 (non-blocking)" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
}

@test "chezmoi-repo: clone-failure — log_warn is emitted (output contains [!])" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_repo_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"[!]"* ]]
}

@test "chezmoi-repo: clone-failure — chezmoi init was still attempted before failure" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  _run_chezmoi_repo_install
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi-repo: clone-failure — no credential or token in output" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_repo_install
  # No credential-style token patterns should appear
  [[ "$output" != *"ghp_"* ]]
  [[ "$output" != *"token"*"@"* ]]
}
