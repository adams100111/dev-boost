load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Spec 10 (system-resilience) — optional-editors profile modules:
#   neovim            — dnf install neovim; bootstrap LazyVim starter (seed-if-absent)
#   jetbrains-toolbox — download+extract JetBrains Toolbox (seed-if-absent)
#
# Both modules are category="editors", profiles=["optional-editors"], Fedora-only,
# idempotent, and verify-guarded.

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  # The git-clone stub creates <dir>/.git when asked — lets us assert the LazyVim
  # starter landed and is treated as "present" on a re-run.
  export STUB_GIT_CLONE_CREATES_DIR=1
}

teardown() {
  base_teardown
}

# Run a module's install.sh directly under the stub PATH with the given env.
_run_install_sh() {
  local module="$1"; shift
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export XDG_CONFIG_HOME='${XDG_CONFIG_HOME}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_GIT_CLONE_CREATES_DIR='${STUB_GIT_CLONE_CREATES_DIR}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export DEVBOOST_TOOLBOX_DIR='${DEVBOOST_TOOLBOX_DIR:-}'
    $* bash '${DEVBOOST_ROOT}/modules/${module}/install.sh'
  " 2>&1
}

# ===========================================================================
# Module metadata
# ===========================================================================

@test "neovim: module.toml is editors category in optional-editors profile" {
  run cat "${DEVBOOST_MODULES_DIR}/neovim/module.toml"
  [ "$status" -eq 0 ]
  [[ "$output" == *'category    = "editors"'* ]] || [[ "$output" == *'category = "editors"'* ]]
  [[ "$output" == *"optional-editors"* ]]
}

@test "jetbrains-toolbox: module.toml is editors category in optional-editors profile" {
  run cat "${DEVBOOST_MODULES_DIR}/jetbrains-toolbox/module.toml"
  [ "$status" -eq 0 ]
  [[ "$output" == *'category    = "editors"'* ]] || [[ "$output" == *'category = "editors"'* ]]
  [[ "$output" == *"optional-editors"* ]]
}

# ===========================================================================
# neovim
# ===========================================================================

@test "neovim: install runs dnf install neovim" {
  run _run_install_sh neovim
  [ "$status" -eq 0 ]
  grep -q 'install -y neovim' "${STUB_DNF_LOG}"
}

@test "neovim: bootstraps the LazyVim starter when ~/.config/nvim is absent" {
  [ ! -d "${XDG_CONFIG_HOME}/nvim" ]
  run _run_install_sh neovim
  [ "$status" -eq 0 ]
  # A LazyVim starter clone was attempted into the nvim config dir.
  grep -q 'clone' "${STUB_GIT_LOG}"
  grep -q 'LazyVim/starter' "${STUB_GIT_LOG}"
  grep -q "${XDG_CONFIG_HOME}/nvim" "${STUB_GIT_LOG}"
  # The starter actually landed (stub creates <dir>/.git).
  [ -d "${XDG_CONFIG_HOME}/nvim" ]
}

@test "neovim: idempotent — does NOT clone when ~/.config/nvim already exists" {
  mkdir -p "${XDG_CONFIG_HOME}/nvim"
  : > "${XDG_CONFIG_HOME}/nvim/init.lua"
  run _run_install_sh neovim
  [ "$status" -eq 0 ]
  # No clone attempted; existing config untouched.
  [ ! -s "${STUB_GIT_LOG}" ] || ! grep -q 'clone' "${STUB_GIT_LOG}"
  [ -f "${XDG_CONFIG_HOME}/nvim/init.lua" ]
}

@test "neovim: honours XDG_CONFIG_HOME for the starter location" {
  local scratch="${BATS_TEST_TMPDIR}/xdg"
  mkdir -p "${scratch}"
  XDG_CONFIG_HOME="${scratch}" run _run_install_sh neovim
  [ "$status" -eq 0 ]
  grep -q "${scratch}/nvim" "${STUB_GIT_LOG}"
}

@test "neovim: verify is command -v nvim" {
  run _module_verify_cmd neovim
  [ "$status" -eq 0 ]
  [[ "$output" == *"command -v nvim"* ]]
}

@test "neovim: unsupported-OS — install command is empty on non-fedora" {
  run _module_install_cmd neovim ubuntu debian
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ===========================================================================
# jetbrains-toolbox
# ===========================================================================

@test "jetbrains-toolbox: downloads + extracts when toolbox binary is absent" {
  export DEVBOOST_TOOLBOX_DIR="${BATS_TEST_TMPDIR}/toolbox/bin"
  [ ! -e "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox" ]
  run _run_install_sh jetbrains-toolbox
  [ "$status" -eq 0 ]
  # A download (curl) was attempted.
  grep -q 'jetbrains' "${STUB_CURL_LOG}"
  # The toolbox binary now exists at the override path.
  [ -e "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox" ]
}

@test "jetbrains-toolbox: honours DEVBOOST_TOOLBOX_DIR override" {
  export DEVBOOST_TOOLBOX_DIR="${BATS_TEST_TMPDIR}/custom-tbx/bin"
  run _run_install_sh jetbrains-toolbox
  [ "$status" -eq 0 ]
  [ -e "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox" ]
}

@test "jetbrains-toolbox: idempotent — skips download when binary already present" {
  export DEVBOOST_TOOLBOX_DIR="${BATS_TEST_TMPDIR}/toolbox/bin"
  mkdir -p "${DEVBOOST_TOOLBOX_DIR}"
  printf '#!/usr/bin/env bash\nexit 0\n' > "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox"
  chmod +x "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox"
  run _run_install_sh jetbrains-toolbox
  [ "$status" -eq 0 ]
  # No download attempted.
  [ ! -s "${STUB_CURL_LOG}" ]
}

@test "jetbrains-toolbox: verify honours DEVBOOST_TOOLBOX_DIR" {
  export DEVBOOST_TOOLBOX_DIR="${BATS_TEST_TMPDIR}/toolbox/bin"
  mkdir -p "${DEVBOOST_TOOLBOX_DIR}"
  printf '#!/usr/bin/env bash\nexit 0\n' > "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox"
  chmod +x "${DEVBOOST_TOOLBOX_DIR}/jetbrains-toolbox"
  vcmd="$(_module_verify_cmd jetbrains-toolbox)"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_TOOLBOX_DIR='${DEVBOOST_TOOLBOX_DIR}'
    ${vcmd}
  "
  [ "$status" -eq 0 ]
}

@test "jetbrains-toolbox: unsupported-OS — install command is empty on non-fedora" {
  run _module_install_cmd jetbrains-toolbox ubuntu debian
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
