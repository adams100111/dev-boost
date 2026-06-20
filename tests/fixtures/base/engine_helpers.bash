# tests/fixtures/base/engine_helpers.bash — shared engine/module helper functions for bats tests.
#
# Load from a bats test file via:
#   load fixtures/base/engine_helpers
#
# Prerequisites: test_helper and fixtures/base/stubs must already be loaded, and
# DEVBOOST_MODULES_DIR must be exported (typically in setup()).

# ---------------------------------------------------------------------------
# _engine_install — run the engine install loop against a module using stub env.
#
# Usage: _engine_install <module_name> [distro [family]] [-- <extra_flags>]
#
# The function signature passes extra flags BEFORE the module name so callers
# can write:
#   _engine_install_flags="--force" _engine_install build-tools fedora fedora
# Instead, we expose a simpler interface: positional (module distro family) and
# the caller sets DEVBOOST_INSTALL_FLAGS before calling if flags are needed.
# ---------------------------------------------------------------------------
_engine_install() {
  local module_name="$1"
  local distro="${2:-fedora}"
  local family="${3:-fedora}"
  local flags="${DEVBOOST_INSTALL_FLAGS:-}"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install ${flags} -- '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# _module_install_cmd — resolve the install command from a module's TOML.
# ---------------------------------------------------------------------------
_module_install_cmd() {
  local module_name="$1" distro="${2:-fedora}" family="${3:-fedora}"
  bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_install_cmd '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# _module_verify_cmd — resolve the verify command from a module's TOML.
# ---------------------------------------------------------------------------
_module_verify_cmd() {
  local module_name="$1"
  bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_verify_cmd '${module_name}'
  " 2>&1
}

# ---------------------------------------------------------------------------
# _run_verify — evaluate a verify command in a subshell with stub env.
# ---------------------------------------------------------------------------
_run_verify() {
  local vcmd="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    ${vcmd}
  " 2>&1
}
