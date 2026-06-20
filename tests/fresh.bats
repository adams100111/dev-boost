load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# This host may have a real `fresh` (or other dev tools) on PATH that would make
# `command -v fresh` succeed and defeat the install/verify tests. We therefore run
# the fresh module under a HERMETIC PATH: the base stub dir + a clean symlink farm
# of exactly the utilities the module/engine need — and NOTHING called `fresh`.
_CLEAN_TOOLS="bash sh env printf mktemp grep sed awk head tail cut tr cat ls dirname \
basename chmod mkdir mv cp rm ln sort uniq wc find xargs sleep test touch tee readlink \
realpath uname id python3 jq"

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  # Build the clean symlink farm (resolve each tool from the still-full PATH).
  _clean_bin="$(mktemp -d)"
  local c src
  for c in ${_CLEAN_TOOLS}; do
    src="$(command -v "${c}" 2>/dev/null)" && ln -sf "${src}" "${_clean_bin}/${c}"
  done
  # Hermetic PATH: stub dir (dnf/rpm/curl/cargo/mise/sudo/code…) then clean farm.
  _hermetic_path="$(base_stub_dir):${_clean_bin}"
}

teardown() {
  [[ -n "${_clean_bin:-}" && -d "${_clean_bin}" ]] && rm -rf "${_clean_bin}"
  base_teardown
}

# Run fresh/install.sh under the hermetic PATH.
_run_module_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_hermetic_path}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_CARGO_LOG='${STUB_CARGO_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_FRESH_INSTALL_VIA='${STUB_FRESH_INSTALL_VIA:-}'
    bash '${DEVBOOST_ROOT}/modules/fresh/install.sh'
  " 2>&1
}

# Run the engine install loop under the hermetic PATH.
_run_engine_fresh() {
  local distro="${1:-fedora}" family="${2:-fedora}"
  bash -c "
    export HOME='${HOME}'
    export PATH='${_hermetic_path}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_CARGO_LOG='${STUB_CARGO_LOG}'
    export STUB_FRESH_INSTALL_VIA='${STUB_FRESH_INSTALL_VIA:-}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- fresh
  " 2>&1
}

# ===========================================================================
# Install channels (rpm → script → cargo), each exercised in isolation
# ===========================================================================

@test "fresh: installs via the Fedora .rpm release channel" {
  export STUB_FRESH_INSTALL_VIA="rpm"
  run _run_module_fresh
  [ "$status" -eq 0 ]
  [[ "$output" == *"installed via rpm"* ]]
  grep -q 'sinelaw/fresh' "${STUB_CURL_LOG}"
  grep -q -- '-U' "${STUB_RPM_LOG}"
}

@test "fresh: falls back to the official install script when rpm fails" {
  export STUB_FRESH_INSTALL_VIA="script"
  run _run_module_fresh
  [ "$status" -eq 0 ]
  [[ "$output" == *"installed via script"* ]]
  grep -q 'install.sh' "${STUB_CURL_LOG}"
}

@test "fresh: falls back to cargo when rpm and script fail" {
  export STUB_FRESH_INSTALL_VIA="cargo"
  run _run_module_fresh
  [ "$status" -eq 0 ]
  [[ "$output" == *"installed via cargo"* ]]
  grep -q 'install --locked fresh-editor' "${STUB_CARGO_LOG}"
}

@test "fresh: all channels fail — module fails NAMING the editor" {
  export STUB_FRESH_INSTALL_VIA="none"
  run _run_module_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"install failed"* ]]
}

# ===========================================================================
# Idempotency + unsupported OS
# ===========================================================================

@test "fresh: idempotent — install short-circuits when fresh already present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fresh"
  chmod +x "$(base_stub_dir)/fresh"
  export STUB_FRESH_INSTALL_VIA="none"  # would fail if it tried to install
  run _run_module_fresh
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
  [ ! -s "${STUB_CARGO_LOG}" ]
}

@test "fresh: engine skips when fresh already on PATH" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fresh"
  chmod +x "$(base_stub_dir)/fresh"
  run _run_engine_fresh fedora fedora
  [ "$status" -eq 0 ]
}

@test "fresh: unsupported-OS — engine reports failure on non-fedora" {
  run _run_engine_fresh ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
