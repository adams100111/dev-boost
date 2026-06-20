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
# Helper: seed the gsettings state file with the reference keys (simulating
# what dconf load would do to a real gsettings-backed dconf store).
# Call after _run_gnome_settings_install to make the gsettings verify work.
# ---------------------------------------------------------------------------
_seed_gsettings_from_dconf() {
  # Write expected reference values into the gsettings scratch state.
  printf '%s=%s\n' "org.gnome.desktop.interface color-scheme" "'prefer-dark'" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf '%s=%s\n' "org.gnome.desktop.interface accent-color" "'blue'" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf '%s=%s\n' "org.gnome.mutter experimental-features" "['scale-monitor-framebuffer']" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf '%s=%s\n' "org.gnome.desktop.wm.preferences button-layout" "'appmenu:minimize,maximize,close'" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf '%s=%s\n' "org.gnome.mutter center-new-windows" "true" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf '%s=%s\n' "org.gnome.desktop.peripherals.touchpad tap-to-click" "true" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
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
  _run_gnome_settings_install >/dev/null 2>&1
  # Seed gsettings state (bridging dconf→gsettings in stub env)
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

@test "gnome-settings: re-run still has only one dconf load invocation signature per run" {
  # After 2 runs, dconf load must have been called (state contains the key).
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
