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
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
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
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
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

@test "chezmoi: requires=[] (binary-only, no deps)" {
  local req
  req="$(grep '^requires' "${DEVBOOST_ROOT}/modules/chezmoi/module.toml")"
  [[ "${req}" == *"[]"* ]]
}

@test "chezmoi: verify field contains 'command -v chezmoi'" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/chezmoi/module.toml")"
  [[ "${vcmd}" == *"command -v chezmoi"* ]]
}

@test "chezmoi: install command references install.sh" {
  grep -q "install.sh" "${DEVBOOST_ROOT}/modules/chezmoi/module.toml"
}

# ===========================================================================
# T016 — success path: binary-only install
# ===========================================================================

@test "chezmoi: success path — install exits 0" {
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
}

@test "chezmoi: success path — chezmoi binary already present is skipped (idempotent)" {
  # chezmoi stub is on PATH; install should log skip and exit 0 without calling curl
  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "chezmoi: binary install path — curl is called when chezmoi absent" {
  local stub_dir
  stub_dir="$(base_stub_dir)"
  # Remove chezmoi stub from PATH so the binary-absent path is exercised.
  rm -f "${stub_dir}/chezmoi"
  # Write a curl stub that emits a tiny installer script placing chezmoi in ~/.local/bin.
  # install.sh runs: sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "${HOME}/.local/bin"
  # The emitted script receives: $0=-- $1=-b $2=<target_dir>
  cat > "${stub_dir}/curl" <<'CURLSTUB'
#!/usr/bin/env bash
log_file="${STUB_CURL_LOG:-/tmp/stub-curl-calls.log}"
printf 'curl %s\n' "$*" >> "${log_file}"
# Emit an installer script; when run as: sh -c "<script>" -- -b <dir>
# positional args inside the script are: $1=-b, $2=<target_dir>
stub_dir="$(dirname "$(command -v curl)")"
printf '#!/usr/bin/env bash\n'
printf 'target_dir="$2"; mkdir -p "$target_dir"; cp "%s/curl" "$target_dir/chezmoi"; chmod +x "$target_dir/chezmoi"\n' "${stub_dir}"
CURLSTUB
  chmod +x "${stub_dir}/curl"

  run _run_chezmoi_install
  [ "$status" -eq 0 ]
  grep -q "curl" "${STUB_CURL_LOG}"
}

# ===========================================================================
# T016 — verify green/red (binary only)
# ===========================================================================

@test "chezmoi: verify is GREEN when chezmoi on PATH" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    command -v chezmoi
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "chezmoi: verify is RED when chezmoi not on PATH" {
  local stub_dir
  stub_dir="$(base_stub_dir)"
  rm -f "${stub_dir}/chezmoi"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${stub_dir}'
    command -v chezmoi
  " 2>&1
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T016 — idempotent re-run (engine verify-guard)
# ===========================================================================

@test "chezmoi: idempotent — engine verify-guard skips install when chezmoi on PATH" {
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
