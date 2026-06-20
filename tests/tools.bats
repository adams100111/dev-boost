load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# DEVBOOST_ROOT is set by test_helper; expose it for subshells.

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
}

teardown() {
  base_teardown
}

# ===========================================================================
# T011 — all modules resolve (TOML exists + has a fedora install key)
# ===========================================================================

@test "all-tools: every per-tool module resolves a fedora install command" {
  local tools=(coreutils git curl wget unzip jq htop ripgrep fd fzf tmux)
  for tool in "${tools[@]}"; do
    local cmd
    cmd="$(_module_install_cmd "${tool}" fedora fedora)"
    [[ -n "${cmd}" ]] || { echo "FAIL: ${tool} returned empty install cmd"; return 1; }
  done
}

# ===========================================================================
# T011 — ripgrep: verify + install + idempotent + unsupported-OS
# ===========================================================================

@test "ripgrep: fedora install command contains 'ripgrep'" {
  local cmd
  cmd="$(_module_install_cmd ripgrep fedora fedora)"
  [[ "${cmd}" == *"ripgrep"* ]]
}

@test "ripgrep: fedora install command is a dnf install invocation" {
  local cmd
  cmd="$(_module_install_cmd ripgrep fedora fedora)"
  [[ "${cmd}" == *"dnf install"* ]]
}

@test "ripgrep: verify uses 'command -v rg' (binary name is rg not ripgrep)" {
  local vcmd
  vcmd="$(_module_verify_cmd ripgrep)"
  [[ "${vcmd}" == *"command -v rg"* ]]
}

@test "ripgrep: verify is GREEN when rg binary is present on PATH" {
  # Place a fake rg binary so command -v rg succeeds.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/rg"
  chmod +x "$(base_stub_dir)/rg"
  local vcmd
  vcmd="$(_module_verify_cmd ripgrep)"
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "ripgrep: verify is RED when rg binary is absent" {
  # Ensure rg is not on PATH (don't install a stub for it).
  rm -f "$(base_stub_dir)/rg"
  local vcmd
  vcmd="$(_module_verify_cmd ripgrep)"
  run _run_verify "${vcmd}"
  [ "$status" -ne 0 ]
}

@test "ripgrep: idempotent — engine skips when rg binary is present" {
  # Place a fake rg so verify passes.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/rg"
  chmod +x "$(base_stub_dir)/rg"
  : > "${STUB_DNF_LOG}"
  run _engine_install ripgrep fedora fedora
  [ "$status" -eq 0 ]
  # dnf must NOT have been called (engine guard fired).
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "ripgrep: engine calls dnf when rg is absent (install step reached)" {
  # Use --force to bypass the verify guard regardless of whether rg is present
  # on the host.  This makes the test host-independent.
  rm -f "$(base_stub_dir)/rg"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install ripgrep fedora fedora || true
  grep -q "ripgrep" "${STUB_DNF_LOG}"
}

@test "ripgrep: unsupported-OS — engine reports unsupported when module has no key for OS" {
  # Run against a non-fedora, non-debian, non-macos OS that has no key.
  # We force OS_DISTRO/OS_FAMILY to something unknown while the ripgrep module
  # only carries fedora/debian/macos keys.
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='arch'
    export OS_FAMILY='arch'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- ripgrep
  " 2>&1
  # Engine must report failure (unsupported), not skip.
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# T011 — fd: verify uses 'command -v fd' (note: fedora pkg is fd-find)
# ===========================================================================

@test "fd: fedora install command contains 'fd-find' (fedora package name)" {
  local cmd
  cmd="$(_module_install_cmd fd fedora fedora)"
  [[ "${cmd}" == *"fd-find"* ]]
}

@test "fd: verify uses 'command -v fd' (binary is fd on fedora)" {
  local vcmd
  vcmd="$(_module_verify_cmd fd)"
  [[ "${vcmd}" == *"command -v fd"* ]]
}

@test "fd: verify is GREEN when fd binary is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fd"
  chmod +x "$(base_stub_dir)/fd"
  local vcmd
  vcmd="$(_module_verify_cmd fd)"
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "fd: idempotent — engine skips when fd binary is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fd"
  chmod +x "$(base_stub_dir)/fd"
  : > "${STUB_DNF_LOG}"
  run _engine_install fd fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "fd: engine calls dnf when fd is absent (install step reached)" {
  # Use --force to bypass the verify guard regardless of whether fd is present
  # on the host.  This makes the test host-independent.
  rm -f "$(base_stub_dir)/fd"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install fd fedora fedora || true
  grep -q "fd-find" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T011 — git: verify + install
# ===========================================================================

@test "git: fedora install command contains 'git'" {
  local cmd
  cmd="$(_module_install_cmd git fedora fedora)"
  [[ "${cmd}" == *"git"* ]]
}

@test "git: verify uses 'command -v git'" {
  local vcmd
  vcmd="$(_module_verify_cmd git)"
  [[ "${vcmd}" == *"command -v git"* ]]
}

@test "git: verify is GREEN when git is on PATH (stub already installed)" {
  # The base stub installs a git stub on PATH already.
  local vcmd
  vcmd="$(_module_verify_cmd git)"
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "git: idempotent — engine skips when git binary is present" {
  # git stub is on PATH from base_setup; verify green → engine must skip.
  : > "${STUB_DNF_LOG}"
  run _engine_install git fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# ===========================================================================
# T011 — tmux: verify + install
# ===========================================================================

@test "tmux: fedora install command contains 'tmux'" {
  local cmd
  cmd="$(_module_install_cmd tmux fedora fedora)"
  [[ "${cmd}" == *"tmux"* ]]
}

@test "tmux: verify uses 'command -v tmux'" {
  local vcmd
  vcmd="$(_module_verify_cmd tmux)"
  [[ "${vcmd}" == *"command -v tmux"* ]]
}

@test "tmux: engine calls dnf when tmux is absent (install step reached)" {
  # Use --force to bypass the verify guard regardless of whether tmux is present
  # on the host.  This makes the test host-independent.
  rm -f "$(base_stub_dir)/tmux"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install tmux fedora fedora || true
  grep -q "tmux" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T011 — coreutils: verify uses 'command -v ls' (always present guard)
# ===========================================================================

@test "coreutils: verify uses 'command -v ls'" {
  local vcmd
  vcmd="$(_module_verify_cmd coreutils)"
  [[ "${vcmd}" == *"command -v ls"* ]]
}

@test "coreutils: verify is GREEN (ls is always present)" {
  local vcmd
  vcmd="$(_module_verify_cmd coreutils)"
  run _run_verify "${vcmd}"
  [ "$status" -eq 0 ]
}

@test "coreutils: idempotent — engine skips when ls is present (always)" {
  : > "${STUB_DNF_LOG}"
  run _engine_install coreutils fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}
