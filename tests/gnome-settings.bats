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
# Helper: run modules/gnome-settings/install.sh in a subshell with full stub env.
# ---------------------------------------------------------------------------
_run_gnome_settings_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    bash '${DEVBOOST_ROOT}/modules/gnome-settings/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: evaluate the module verify expression in a subshell (stub env).
# The verify expression from module.toml uses gsettings get, but in the stub
# environment we check that the dconf dump was loaded (state file has the key).
# We also support seeding the gsettings state from the dconf load to let the
# canonical verify expression pass.
# ---------------------------------------------------------------------------
_run_gnome_settings_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    [ \"\$(gsettings get org.gnome.desktop.interface color-scheme)\" = \"'prefer-dark'\" ]
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: seed the gsettings state file by parsing STUB_DCONF_STATE_FILE.
# Only keys actually present in the dconf state (written by a real install run)
# are bridged into the gsettings scratch store, so GREEN depends causally on
# install having succeeded and written the dconf state.
#
# The dconf dump uses INI-style sections like [desktop/interface] and bare
# key=value pairs.  We map section paths to org.gnome.* schema names and emit
# one "schema key=value" line per entry into STUB_GSETTINGS_STATE_FILE.
# ---------------------------------------------------------------------------
_seed_gsettings_from_dconf() {
  local section="" schema="" key="" value="" line
  # section-path → org.gnome.* schema mapping
  _dconf_section_to_schema() {
    case "$1" in
      desktop/interface)           printf 'org.gnome.desktop.interface' ;;
      desktop/wm/preferences)      printf 'org.gnome.desktop.wm.preferences' ;;
      mutter)                      printf 'org.gnome.mutter' ;;
      desktop/peripherals/touchpad) printf 'org.gnome.desktop.peripherals.touchpad' ;;
      *)                           printf '' ;;
    esac
  }

  # Abort if the dconf state file is empty or absent — install did not run.
  [[ -s "${STUB_DCONF_STATE_FILE}" ]] || return 1

  while IFS= read -r line; do
    # Skip blank lines and comment lines.
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    # Section header: [desktop/interface]
    if [[ "${line}" == \[*\] ]]; then
      section="${line#[}"
      section="${section%]}"
      schema="$(_dconf_section_to_schema "${section}")"
      continue
    fi
    # Key=value pair within a known section.
    if [[ -n "${schema}" && "${line}" == *=* ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      printf '%s %s=%s\n' "${schema}" "${key}" "${value}" \
        >> "${STUB_GSETTINGS_STATE_FILE}"
    fi
  done < "${STUB_DCONF_STATE_FILE}"
}

# ===========================================================================
# T006 — module shape
# ===========================================================================

@test "gnome-settings: modules/gnome-settings/module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-settings/module.toml" ]
}

@test "gnome-settings: modules/gnome-settings/install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-settings/install.sh" ]
}

@test "gnome-settings: gnome.dconf data file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf" ]
}

@test "gnome-settings: module.toml category is gnome" {
  grep -q 'category.*=.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-settings/module.toml"
}

@test "gnome-settings: module.toml requires is empty" {
  # requires = [] — no dependencies
  grep -q 'requires.*=.*\[\]' "${DEVBOOST_ROOT}/modules/gnome-settings/module.toml"
}

@test "gnome-settings: module.toml verify checks color-scheme" {
  grep -q 'color-scheme' "${DEVBOOST_ROOT}/modules/gnome-settings/module.toml"
}

@test "gnome-settings: module.toml install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/gnome-settings/module.toml"
}

# ===========================================================================
# T006 — gnome.dconf data file content
# ===========================================================================

@test "gnome-settings: gnome.dconf contains color-scheme key" {
  grep -q 'color-scheme' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf color-scheme is prefer-dark" {
  grep -q "color-scheme='prefer-dark'" "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf contains accent-color key" {
  grep -q 'accent-color' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf contains mutter experimental-features" {
  grep -q 'experimental-features' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf experimental-features includes scale-monitor-framebuffer" {
  grep -q 'scale-monitor-framebuffer' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf contains button-layout key" {
  grep -q 'button-layout' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf button-layout is appmenu:minimize,maximize,close" {
  grep -q "button-layout='appmenu:minimize,maximize,close'" "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf contains center-new-windows key" {
  grep -q 'center-new-windows' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf center-new-windows is true" {
  grep -q 'center-new-windows=true' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf contains tap-to-click key" {
  grep -q 'tap-to-click' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf tap-to-click is true" {
  grep -q 'tap-to-click=true' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf does NOT contain enabled-extensions" {
  # enabled-extensions is owned by gnome-extensions module (F2)
  ! grep -q 'enabled-extensions' "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

@test "gnome-settings: gnome.dconf does NOT contain secrets or tokens" {
  ! grep -qiE 'ghp_[A-Za-z0-9]+|password\s*=|secret\s*=|ANTHROPIC_API_KEY\s*=' \
    "${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"
}

# ===========================================================================
# T006 — install: dconf load called with the dump file
# ===========================================================================

@test "gnome-settings: install.sh exits 0 on GNOME system" {
  run _run_gnome_settings_install
  [ "$status" -eq 0 ]
}

@test "gnome-settings: install.sh calls dconf load" {
  run _run_gnome_settings_install
  [ "$status" -eq 0 ]
  grep -qF 'dconf load' "${STUB_DCONF_LOG}"
}

@test "gnome-settings: install.sh loads the gnome.dconf dump file" {
  run _run_gnome_settings_install
  [ "$status" -eq 0 ]
  # The dconf stub records the dump content in the state file
  grep -qF 'color-scheme' "${STUB_DCONF_STATE_FILE}"
}

# ===========================================================================
# T006 — install: reference keys applied (check dconf state)
# ===========================================================================

@test "gnome-settings: apply sets color-scheme to prefer-dark in dconf state" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF "color-scheme='prefer-dark'" "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply sets accent-color in dconf state" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF 'accent-color' "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply sets mutter experimental-features (scale-monitor-framebuffer)" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF 'scale-monitor-framebuffer' "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply sets button-layout to appmenu:minimize,maximize,close" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF "button-layout='appmenu:minimize,maximize,close'" "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply sets center-new-windows to true" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF 'center-new-windows=true' "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply sets tap-to-click to true" {
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF 'tap-to-click=true' "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: apply does NOT set enabled-extensions in dconf state" {
  _run_gnome_settings_install >/dev/null 2>&1
  ! grep -qF 'enabled-extensions' "${STUB_DCONF_STATE_FILE}"
}

# ===========================================================================
# T006 — verify: RED before install, GREEN after (via gsettings stub)
# ===========================================================================

@test "gnome-settings: verify is RED before install (gsettings returns empty)" {
  # No install has run; gsettings state file is empty — verify must fail.
  run _run_gnome_settings_verify
  [ "$status" -ne 0 ]
}

@test "gnome-settings: verify is GREEN after install + gsettings state seeded" {
  # Assert install succeeded FIRST — GREEN must depend on a successful install.
  run _run_gnome_settings_install
  [ "$status" -eq 0 ]
  # Bridge dconf state (written by install) into the gsettings scratch store.
  # _seed_gsettings_from_dconf reads STUB_DCONF_STATE_FILE; fails if it is empty
  # (i.e. if install did not actually write any dconf state).
  _seed_gsettings_from_dconf
  run _run_gnome_settings_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T006 — idempotency: re-run produces no new dconf load calls' state
# ===========================================================================

@test "gnome-settings: re-run is idempotent (exits 0 on second call)" {
  _run_gnome_settings_install >/dev/null 2>&1
  run _run_gnome_settings_install
  [ "$status" -eq 0 ]
}

@test "gnome-settings: re-run does not corrupt dconf state (color-scheme still present)" {
  _run_gnome_settings_install >/dev/null 2>&1
  _run_gnome_settings_install >/dev/null 2>&1
  grep -qF "color-scheme='prefer-dark'" "${STUB_DCONF_STATE_FILE}"
}

@test "gnome-settings: re-run ran dconf load on each of the two runs (count >= 2)" {
  # After 2 runs, dconf load must have been called at least twice (once per run).
  _run_gnome_settings_install >/dev/null 2>&1
  _run_gnome_settings_install >/dev/null 2>&1
  local count
  count="$(grep -c 'dconf load' "${STUB_DCONF_LOG}" || printf '0')"
  [ "${count}" -ge 2 ]
}

# ===========================================================================
# T006 — GNOME absent: unsupported failure (not skip)
# ===========================================================================

@test "gnome-settings: exits non-zero when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_settings_install
  [ "$status" -ne 0 ]
}

@test "gnome-settings: names the failure when GNOME is absent (unsupported)" {
  base_gnome_present_off
  run _run_gnome_settings_install
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome-settings: does not load dconf when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_settings_install
  # dconf load must NOT have been called
  ! grep -qF 'dconf load' "${STUB_DCONF_LOG}"
}
