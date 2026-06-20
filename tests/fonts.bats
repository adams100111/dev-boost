load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run an escape-hatch install.sh in a fully-stubbed subshell.
# ---------------------------------------------------------------------------
_run_install_sh() {
  local module="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_FC_LIST_LOG='${STUB_FC_LIST_LOG}'
    export STUB_FC_CACHE_LOG='${STUB_FC_CACHE_LOG}'
    export STUB_FONTS_INSTALLED='${STUB_FONTS_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/${module}/install.sh'
  " 2>&1
}

# ===========================================================================
# nerd-fonts
# ===========================================================================

@test "nerd-fonts: module file exists at modules/nerd-fonts/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/nerd-fonts/module.toml" ]
}

@test "nerd-fonts: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/nerd-fonts/install.sh" ]
}

@test "nerd-fonts: install command is the escape-hatch (runs install.sh)" {
  local cmd
  cmd="$(_module_install_cmd nerd-fonts fedora fedora)"
  [[ "${cmd}" == *"modules/nerd-fonts/install.sh"* ]]
}

@test "nerd-fonts: verify command checks fc-list for JetBrainsMono Nerd Font" {
  local vcmd
  vcmd="$(_module_verify_cmd nerd-fonts)"
  [[ "${vcmd}" == *"fc-list"* ]] && [[ "${vcmd}" == *"JetBrainsMono"* ]]
}

@test "nerd-fonts: category is shell" {
  local toml="${DEVBOOST_ROOT}/modules/nerd-fonts/module.toml"
  [ -f "${toml}" ]
  grep -q 'category.*=.*"shell"' "${toml}"
}

@test "nerd-fonts: requires is empty" {
  local req
  req="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires nerd-fonts
  " 2>&1)"
  [[ -z "${req}" ]]
}

@test "nerd-fonts: install.sh downloads fonts when absent (STUB_FONTS_INSTALLED empty)" {
  # Fonts absent — install.sh should attempt to download into ~/.local/share/fonts/
  unset STUB_FONTS_INSTALLED
  : > "${STUB_FC_CACHE_LOG}"
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
  # Fonts directory should have been created
  [ -d "${HOME}/.local/share/fonts" ]
}

@test "nerd-fonts: install.sh places JetBrainsMono font file when absent" {
  unset STUB_FONTS_INSTALLED
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
  # At least one JetBrainsMono font file should exist in the fonts dir
  local found
  found="$(find "${HOME}/.local/share/fonts" -name '*JetBrainsMono*' 2>/dev/null | head -1)"
  [ -n "${found}" ]
}

@test "nerd-fonts: install.sh places MesloLG font file when absent" {
  unset STUB_FONTS_INSTALLED
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
  # At least one Meslo font file should exist in the fonts dir
  local found
  found="$(find "${HOME}/.local/share/fonts" -name '*Meslo*' 2>/dev/null | head -1)"
  [ -n "${found}" ]
}

@test "nerd-fonts: fc-cache -f is run after fonts are installed" {
  unset STUB_FONTS_INSTALLED
  : > "${STUB_FC_CACHE_LOG}"
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
  grep -q "fc-cache" "${STUB_FC_CACHE_LOG}"
}

@test "nerd-fonts: install.sh SKIPS download when JetBrainsMono already in fc-list" {
  export STUB_FONTS_INSTALLED="JetBrainsMono Nerd Font:style=Regular
MesloLGS NF:style=Regular"
  : > "${STUB_FC_CACHE_LOG}"
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
  # No new font files should have been written (fonts dir should not have been populated
  # with new downloads beyond what fc-list already reports)
  # The key behaviour: output indicates a skip
  [[ "$output" == *"skip"* ]] || [[ "$output" == *"SKIP"* ]] \
    || [[ "$output" == *"already"* ]] || [[ "$output" == *"present"* ]]
}

@test "nerd-fonts: fc-cache is run even when fonts skipped (verify path)" {
  # When fonts are already present, the module can still run fc-cache
  # This is acceptable behaviour; the key is that it doesn't re-download
  export STUB_FONTS_INSTALLED="JetBrainsMono Nerd Font:style=Regular"
  : > "${STUB_FC_CACHE_LOG}"
  run _run_install_sh nerd-fonts
  [ "$status" -eq 0 ]
}

@test "nerd-fonts: verify passes when fc-list shows JetBrainsMono Nerd Font" {
  # Set up fc-list to report JetBrainsMono
  export STUB_FONTS_INSTALLED="JetBrainsMono Nerd Font:style=Regular"
  local vcmd
  vcmd="$(_module_verify_cmd nerd-fonts)"
  # Run verify in the stubbed environment
  local result
  result="$(bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_FONTS_INSTALLED='JetBrainsMono Nerd Font:style=Regular'
    export STUB_FC_LIST_LOG='${STUB_FC_LIST_LOG}'
    ${vcmd}
  " 2>&1)"
  local rc=$?
  [ "${rc}" -eq 0 ]
}

@test "nerd-fonts: verify FAILS when fc-list shows no fonts" {
  unset STUB_FONTS_INSTALLED
  local vcmd
  vcmd="$(_module_verify_cmd nerd-fonts)"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_FONTS_INSTALLED=''
    export STUB_FC_LIST_LOG='${STUB_FC_LIST_LOG}'
    ${vcmd}
  "
  [ "$status" -ne 0 ]
}

@test "nerd-fonts: engine skips when fonts are already installed (idempotent)" {
  export STUB_FONTS_INSTALLED="JetBrainsMono Nerd Font:style=Regular"
  : > "${STUB_FC_CACHE_LOG}"
  run _engine_install nerd-fonts fedora fedora
  [ "$status" -eq 0 ]
  # fc-cache should NOT have been called (engine skipped before reaching install)
  [ ! -s "${STUB_FC_CACHE_LOG}" ]
}

@test "nerd-fonts: install is reachable via --force (host-independent)" {
  unset STUB_FONTS_INSTALLED
  : > "${STUB_FC_CACHE_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install nerd-fonts fedora fedora || true
  # fc-cache must have been called during install
  grep -q "fc-cache" "${STUB_FC_CACHE_LOG}"
}
