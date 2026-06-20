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
    export DEVBOOST_DOTFILES_REPO='${DEVBOOST_DOTFILES_REPO:-}'
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
    export DEVBOOST_DOTFILES_REPO='${DEVBOOST_DOTFILES_REPO:-}'
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
# T016 — success path: install + init (no repo configured)
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
  # Remove chezmoi stub so need_cmd triggers install; keep a replacement stub so
  # chezmoi init succeeds after dnf installs it.
  local stub_dir
  stub_dir="$(base_stub_dir)"
  rm -f "${stub_dir}/chezmoi"

  # Write a post-install stub that need_cmd/dnf will make available via PATH.
  # need_cmd re-checks command -v after dnf runs; since dnf is a stub that exits 0
  # the binary must be present on PATH. Re-create the stub at the same path.
  cat > "${stub_dir}/chezmoi" <<'STUB'
#!/usr/bin/env bash
log_file="${STUB_CHEZMOI_LOG:-/tmp/stub-chezmoi-calls.log}"
printf 'chezmoi %s\n' "$*" >> "${log_file}"
if [[ "$1" == "init" ]]; then
  mkdir -p "${HOME}/.local/share/chezmoi"
fi
exit 0
STUB
  chmod +x "${stub_dir}/chezmoi"

  # Temporarily hide the stub so need_cmd sees it as absent, then dnf re-exposes it.
  # Achieve this by writing a wrapper dnf that installs the stub after logging.
  cat > "${stub_dir}/dnf" <<DNFSTUB
#!/usr/bin/env bash
log_file="\${STUB_DNF_LOG:-/tmp/stub-dnf-calls.log}"
printf 'dnf %s\n' "\$*" >> "\${log_file}"
exit 0
DNFSTUB
  chmod +x "${stub_dir}/dnf"

  # Hide chezmoi initially: rename it aside; dnf stub will not actually install it,
  # but since PATH already has the stub dir, need_cmd will find it after dnf runs.
  # Instead, use a sentinel file approach: start with chezmoi absent, dnf logs the
  # install, then chezmoi is present (we put the stub back after dnf runs via a
  # wrapper script).
  #
  # Simpler: write a chezmoi stub that exists at PATH from the start but wrap
  # need_cmd's check via a second PATH entry that lacks chezmoi at first.
  # The cleanest approach: use an intermediate dir prepended before the stub dir.
  local hidden_dir
  hidden_dir="$(mktemp -d)"
  # Put chezmoi only in stub_dir (not hidden_dir). Then prepend hidden_dir so
  # initially `command -v chezmoi` fails, but after dnf the PATH still has stub_dir.
  # We accomplish this by temporarily moving the chezmoi stub out, running the
  # install (dnf will log), then putting it back — but set -e would abort on the
  # 127. Instead, pre-create the stub in a second dir that gets added to PATH
  # by need_cmd after install. Since that's internal, the simplest deterministic
  # approach: the dnf stub re-creates chezmoi in the bin dir as a side-effect.

  # Reset and use a dnf stub that re-creates chezmoi on install:
  cat > "${stub_dir}/dnf" <<DNFSTUB2
#!/usr/bin/env bash
log_file="\${STUB_DNF_LOG:-/tmp/stub-dnf-calls.log}"
printf 'dnf %s\n' "\$*" >> "\${log_file}"
# Re-create chezmoi stub so need_cmd finds it after install
cat > "${stub_dir}/chezmoi" <<'CHEZMOI'
#!/usr/bin/env bash
log_file2="\${STUB_CHEZMOI_LOG:-/tmp/stub-chezmoi-calls.log}"
printf 'chezmoi %s\n' "\$*" >> "\${log_file2}"
if [[ "\$1" == "init" ]]; then
  mkdir -p "\${HOME}/.local/share/chezmoi"
fi
exit 0
CHEZMOI
chmod +x "${stub_dir}/chezmoi"
exit 0
DNFSTUB2
  chmod +x "${stub_dir}/dnf"

  # Now actually remove chezmoi so need_cmd triggers the install
  rm -f "${stub_dir}/chezmoi"

  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  # dnf must have been called to install chezmoi
  grep -q "chezmoi" "${STUB_DNF_LOG}"
  rm -rf "${hidden_dir}"
}

# ===========================================================================
# T016 — DEVBOOST_DOTFILES_REPO clone path
# ===========================================================================

@test "chezmoi: with DEVBOOST_DOTFILES_REPO set — init receives the repo argument" {
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  # The stub must have logged: chezmoi init --apply <repo>
  grep -q "init --apply https://github.com/testuser/dotfiles" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi: with DEVBOOST_DOTFILES_REPO set — no credential or token on command line" {
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  # Output must not contain token-style strings
  [[ "$output" != *"ghp_"* ]]
  [[ "$output" != *"token"*"@"* ]]
}

@test "chezmoi: without DEVBOOST_DOTFILES_REPO — local init (no repo arg) succeeds" {
  unset DEVBOOST_DOTFILES_REPO
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  # Log should contain 'chezmoi init' but NOT '--apply'
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
  ! grep -q "\-\-apply" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi: without DEVBOOST_DOTFILES_REPO — output mentions no dotfiles repo configured" {
  unset DEVBOOST_DOTFILES_REPO
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"DEVBOOST_DOTFILES_REPO"* ]]
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
  # Use a stub-only PATH so we don't accidentally find the real host chezmoi.
  local stub_dir
  stub_dir="$(base_stub_dir)"
  rm -f "${stub_dir}/chezmoi"
  mkdir -p "${HOME}/.local/share/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${stub_dir}'
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
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
}

@test "chezmoi: clone-failure — log_warn is emitted (output contains [!])" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"[!]"* ]]
}

@test "chezmoi: clone-failure — chezmoi init was still attempted before failure" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
  _run_chezmoi_install
  grep -q "chezmoi init" "${STUB_CHEZMOI_LOG}"
}

@test "chezmoi: clone-failure — no credential or token in output" {
  export STUB_CHEZMOI_CLONE_FAIL=1
  export DEVBOOST_DOTFILES_REPO="https://github.com/testuser/dotfiles"
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
