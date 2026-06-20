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
# Helper: source lib/gnome.sh + its deps in a subshell with full stub env.
# ---------------------------------------------------------------------------
_gnome_run() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_GEXT_MISMATCH_UUID='${STUB_GEXT_MISMATCH_UUID:-}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/pkg.sh'
    source '${DEVBOOST_ROOT}/lib/gnome.sh'
    $1
  " 2>&1
}

# ===========================================================================
# gnome_require
# ===========================================================================

@test "gnome_require: succeeds when GNOME is present (STUB_GNOME_PRESENT=1)" {
  # Default setup: STUB_GNOME_PRESENT=1, XDG_CURRENT_DESKTOP=GNOME
  run _gnome_run 'gnome_require'
  [ "$status" -eq 0 ]
}

@test "gnome_require: fails with 'unsupported' when GNOME is absent" {
  base_gnome_present_off
  run _gnome_run 'gnome_require'
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome_require: detects GNOME via XDG_CURRENT_DESKTOP even when shell --version fails" {
  # Make gnome-shell --version fail but set XDG_CURRENT_DESKTOP=GNOME
  base_gnome_present_off
  export XDG_CURRENT_DESKTOP="GNOME"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='GNOME'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GNOME_PRESENT='0'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/pkg.sh'
    source '${DEVBOOST_ROOT}/lib/gnome.sh'
    gnome_require
  " 2>&1
  [ "$status" -eq 0 ]
}

# ===========================================================================
# gnome_shell_version
# ===========================================================================

@test "gnome_shell_version: prints major version number from stub" {
  export STUB_GNOME_SHELL_VERSION="GNOME Shell 47.0"
  run _gnome_run 'gnome_shell_version'
  [ "$status" -eq 0 ]
  [ "$output" = "47" ]
}

@test "gnome_shell_version: handles version with patch (e.g. 46.2)" {
  export STUB_GNOME_SHELL_VERSION="GNOME Shell 46.2"
  run _gnome_run 'gnome_shell_version'
  [ "$status" -eq 0 ]
  [ "$output" = "46" ]
}

# ===========================================================================
# ext_install
# ===========================================================================

@test "ext_install: calls gext install with the UUID" {
  run _gnome_run 'ext_install "clipboard-indicator@tudmotu.com"'
  [ "$status" -eq 0 ]
  grep -qF 'gext install clipboard-indicator@tudmotu.com' "${STUB_GEXT_LOG}"
}

@test "ext_install: creates the extension directory with metadata.json" {
  run _gnome_run 'ext_install "clipboard-indicator@tudmotu.com"'
  [ "$status" -eq 0 ]
  [ -f "${HOME}/.local/share/gnome-shell/extensions/clipboard-indicator@tudmotu.com/metadata.json" ]
}

@test "ext_install: skips gext call when extension dir already exists" {
  local ext_dir="${HOME}/.local/share/gnome-shell/extensions/clipboard-indicator@tudmotu.com"
  mkdir -p "${ext_dir}"
  printf '{"uuid":"clipboard-indicator@tudmotu.com","name":"Test"}\n' > "${ext_dir}/metadata.json"
  run _gnome_run 'ext_install "clipboard-indicator@tudmotu.com"'
  [ "$status" -eq 0 ]
  # gext log should be empty (no install call)
  [ ! -s "${STUB_GEXT_LOG}" ]
}

# ===========================================================================
# ext_verify_author
# ===========================================================================

@test "ext_verify_author: passes when metadata uuid matches" {
  # First install the extension via stub
  local uuid="clipboard-indicator@tudmotu.com"
  local ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
  mkdir -p "${ext_dir}"
  printf '{"uuid":"%s","name":"Clipboard Indicator"}\n' "${uuid}" > "${ext_dir}/metadata.json"
  run _gnome_run "ext_verify_author '${uuid}'"
  [ "$status" -eq 0 ]
}

@test "ext_verify_author: fails with named error when UUID mismatches (STUB_GEXT_MISMATCH_UUID)" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  local uuid="clipboard-indicator@tudmotu.com"
  # First create the extension dir with mismatched uuid
  local ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
  mkdir -p "${ext_dir}"
  printf '{"uuid":"evil@attacker.example","name":"Evil"}\n' > "${ext_dir}/metadata.json"
  run _gnome_run "ext_verify_author '${uuid}'"
  [ "$status" -ne 0 ]
  [[ "$output" == *"${uuid}"* ]] || [[ "$output" == *"mismatch"* ]] || [[ "$output" == *"author"* ]]
}

# ===========================================================================
# ext_enable
# ===========================================================================

@test "ext_enable: adds UUID to enabled-extensions list" {
  local uuid="clipboard-indicator@tudmotu.com"
  run _gnome_run "ext_enable '${uuid}'"
  [ "$status" -eq 0 ]
  # Check the state file contains the UUID
  grep -qF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}"
}

@test "ext_enable: does not duplicate UUID on second call" {
  local uuid="clipboard-indicator@tudmotu.com"
  # Enable twice in sequence
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/pkg.sh'
    source '${DEVBOOST_ROOT}/lib/gnome.sh'
    ext_enable '${uuid}'
    ext_enable '${uuid}'
  " 2>&1
  [ "$status" -eq 0 ]
  # The UUID must appear exactly once in the enabled-extensions value
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "$count" -eq 1 ]
}

@test "ext_enable: result list contains the UUID after enabling" {
  local uuid="caffeine@patapon.info"
  run _gnome_run "ext_enable '${uuid}'"
  [ "$status" -eq 0 ]
  grep -qF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}"
}

@test "ext_enable: enabling two distinct UUIDs — both appear in list" {
  local uuid1="clipboard-indicator@tudmotu.com"
  local uuid2="caffeine@patapon.info"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/pkg.sh'
    source '${DEVBOOST_ROOT}/lib/gnome.sh'
    ext_enable '${uuid1}'
    ext_enable '${uuid2}'
  " 2>&1
  [ "$status" -eq 0 ]
  grep -qF "${uuid1}" "${STUB_GSETTINGS_STATE_FILE}"
  grep -qF "${uuid2}" "${STUB_GSETTINGS_STATE_FILE}"
}

# ===========================================================================
# dconf_load_managed
# ===========================================================================

@test "dconf_load_managed: calls dconf load with the dump file" {
  # Create a minimal dconf dump file
  local dump_file="${BATS_TEST_TMPDIR}/test.dconf"
  printf '[/org/gnome/desktop/interface]\ncolor-scheme='"'"'prefer-dark'"'"'\n' > "${dump_file}"
  run _gnome_run "dconf_load_managed '${dump_file}'"
  [ "$status" -eq 0 ]
  grep -qF 'dconf load' "${STUB_DCONF_LOG}"
}

@test "dconf_load_managed: records the dump content in state file" {
  local dump_file="${BATS_TEST_TMPDIR}/test.dconf"
  printf '[/org/gnome/desktop/interface]\ncolor-scheme='"'"'prefer-dark'"'"'\n' > "${dump_file}"
  run _gnome_run "dconf_load_managed '${dump_file}'"
  [ "$status" -eq 0 ]
  grep -qF 'color-scheme' "${STUB_DCONF_STATE_FILE}"
}

@test "dconf_load_managed: is idempotent (second call succeeds)" {
  local dump_file="${BATS_TEST_TMPDIR}/test.dconf"
  printf '[/org/gnome/desktop/interface]\ncolor-scheme='"'"'prefer-dark'"'"'\n' > "${dump_file}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/pkg.sh'
    source '${DEVBOOST_ROOT}/lib/gnome.sh'
    dconf_load_managed '${dump_file}'
    dconf_load_managed '${dump_file}'
  " 2>&1
  [ "$status" -eq 0 ]
}
