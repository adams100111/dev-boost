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

_USER_THEMES_UUID="user-theme@gnome-shell-extensions.gcampax.github.com"

# ---------------------------------------------------------------------------
# Helper: run gnome-theme-bundle install.sh in a subshell.
# ---------------------------------------------------------------------------
_run_theme_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_GEXT_MISMATCH_UUID='${STUB_GEXT_MISMATCH_UUID:-}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_FC_CACHE_LOG='${STUB_FC_CACHE_LOG}'
    export STUB_COPR_ENABLED='${STUB_COPR_ENABLED:-}'
    bash '${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: run gnome-theme-bundle install.sh --verify-only in a subshell.
# ---------------------------------------------------------------------------
_run_theme_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    export STUB_FONTS_INSTALLED='${STUB_FONTS_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh' --verify-only
  " 2>&1
}

# ===========================================================================
# T013 — module shape
# ===========================================================================

@test "gnome-theme-bundle: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml" ]
}

@test "gnome-theme-bundle: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh" ]
}

@test "gnome-theme-bundle: module.toml category is gnome" {
  grep -q 'category.*=.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml"
}

@test "gnome-theme-bundle: module.toml requires gnome-settings" {
  grep -q 'gnome-settings' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml"
}

@test "gnome-theme-bundle: module.toml profiles is gnome-theme (OPT-IN, not gnome)" {
  grep -q 'gnome-theme' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml"
  ! grep -qE 'profiles.*=.*\[.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml"
}

@test "gnome-theme-bundle: module.toml install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/module.toml"
}

@test "gnome-theme-bundle: install.sh references WhiteSur-gtk-theme URL" {
  grep -q 'vinceliuice/WhiteSur-gtk-theme' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh"
}

@test "gnome-theme-bundle: install.sh references pinned tag" {
  grep -q '2024-11-18' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh"
}

@test "gnome-theme-bundle: install.sh uses git clone not curl/wget for theme" {
  grep -q 'git clone' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh"
  ! grep -qE '(curl|wget).*gnome-look' "${DEVBOOST_ROOT}/modules/gnome-theme-bundle/install.sh"
}

# ===========================================================================
# T013 — install: User Themes extension installed + enabled
# ===========================================================================

@test "gnome-theme-bundle: install exits 0 on GNOME system" {
  run _run_theme_install
  [ "$status" -eq 0 ]
}

@test "gnome-theme-bundle: installs User Themes extension via gext" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF "gext install ${_USER_THEMES_UUID}" "${STUB_GEXT_LOG}"
}

@test "gnome-theme-bundle: User Themes extension author-verify passes" {
  # No mismatch UUID set; install must succeed (author-verify passed).
  run _run_theme_install
  [ "$status" -eq 0 ]
}

@test "gnome-theme-bundle: User Themes extension enabled after install" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  local enabled
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  [[ "${enabled}" == *"${_USER_THEMES_UUID}"* ]]
}

# ===========================================================================
# T013 — install: git clone called for vinceliuice theme
# ===========================================================================

@test "gnome-theme-bundle: git clone called for vinceliuice theme" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'git clone' "${STUB_GIT_LOG}"
}

@test "gnome-theme-bundle: git clone references WhiteSur-gtk-theme URL" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'vinceliuice/WhiteSur-gtk-theme' "${STUB_GIT_LOG}"
}

@test "gnome-theme-bundle: git clone uses pinned tag" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF '2024-11-18' "${STUB_GIT_LOG}"
}

@test "gnome-theme-bundle: theme dir created after install" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  [ -d "${HOME}/.themes/WhiteSur-Dark" ]
}

@test "gnome-theme-bundle: git clone skipped when theme dir already present (idempotent)" {
  # Pre-create the theme dir to simulate already installed.
  mkdir -p "${HOME}/.themes/WhiteSur-Dark"
  run _run_theme_install
  [ "$status" -eq 0 ]
  # git clone should NOT have been called.
  ! grep -qF 'git clone' "${STUB_GIT_LOG}"
}

# ===========================================================================
# T013 — install: packages installed
# ===========================================================================

@test "gnome-theme-bundle: installs papirus-icon-theme via dnf" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'papirus-icon-theme' "${STUB_DNF_LOG}"
}

@test "gnome-theme-bundle: installs bibata-cursor-themes via dnf" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'bibata-cursor-themes' "${STUB_DNF_LOG}"
}

@test "gnome-theme-bundle: installs rsms-inter-fonts via dnf" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'rsms-inter-fonts' "${STUB_DNF_LOG}"
}

@test "gnome-theme-bundle: runs fc-cache after font install" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'fc-cache' "${STUB_FC_CACHE_LOG}"
}

# ===========================================================================
# T013 — install: gsettings theme keys applied
# ===========================================================================

@test "gnome-theme-bundle: sets gtk-theme to WhiteSur-Dark" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  local val
  val="$(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null || printf '')"
  [[ "${val}" == *"WhiteSur-Dark"* ]]
}

@test "gnome-theme-bundle: sets icon-theme to Papirus-Dark" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  local val
  val="$(gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null || printf '')"
  [[ "${val}" == *"Papirus-Dark"* ]]
}

@test "gnome-theme-bundle: sets cursor-theme to Bibata-Modern-Classic" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  local val
  val="$(gsettings get org.gnome.desktop.interface cursor-theme 2>/dev/null || printf '')"
  [[ "${val}" == *"Bibata-Modern-Classic"* ]]
}

@test "gnome-theme-bundle: sets font-name to Inter" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  local val
  val="$(gsettings get org.gnome.desktop.interface font-name 2>/dev/null || printf '')"
  [[ "${val}" == *"Inter"* ]]
}

# ===========================================================================
# T013 — COPR: enabled for Bibata cursor
# ===========================================================================

@test "gnome-theme-bundle: enables COPR for Bibata cursor when not present" {
  run _run_theme_install
  [ "$status" -eq 0 ]
  grep -qF 'copr enable' "${STUB_DNF_LOG}"
}

@test "gnome-theme-bundle: skips COPR enable when Bibata COPR already present" {
  export STUB_COPR_ENABLED="ful1e5/Bibata-Cursor"
  run _run_theme_install
  [ "$status" -eq 0 ]
  ! grep -qF 'copr enable' "${STUB_DNF_LOG}"
}

# ===========================================================================
# T013 — verify: RED before install, GREEN after
# ===========================================================================

@test "gnome-theme-bundle: --verify-only exits non-zero before install (pristine)" {
  run _run_theme_verify
  [ "$status" -ne 0 ]
}

@test "gnome-theme-bundle: --verify-only exits 0 after install (all state present)" {
  # Run install first so gsettings state + theme dir are set.
  _run_theme_install >/dev/null 2>&1
  # Set RPM and font knobs so verify passes those checks too.
  export STUB_RPM_INSTALLED="papirus-icon-theme bibata-cursor-themes rsms-inter-fonts"
  export STUB_FONTS_INSTALLED="Inter:style=Regular"
  run _run_theme_verify
  [ "$status" -eq 0 ]
}

@test "gnome-theme-bundle: verify names User Themes not enabled when absent" {
  run _run_theme_verify
  [ "$status" -ne 0 ]
  [[ "$output" == *"User Themes"* ]] || [[ "$output" == *"user-theme"* ]]
}

@test "gnome-theme-bundle: verify names theme dir absent when not installed" {
  # Set gsettings state manually: User Themes enabled + gtk-theme set.
  printf 'org.gnome.shell enabled-extensions=['"'"'%s'"'"']\n' "${_USER_THEMES_UUID}" \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  printf 'org.gnome.desktop.interface gtk-theme='"'"'WhiteSur-Dark'"'"'\n' \
    >> "${STUB_GSETTINGS_STATE_FILE}"
  export STUB_RPM_INSTALLED="papirus-icon-theme"
  export STUB_FONTS_INSTALLED="Inter:style=Regular"
  run _run_theme_verify
  # Should fail because theme dir doesn't exist.
  [ "$status" -ne 0 ]
  [[ "$output" == *"WhiteSur-Dark"* ]] || [[ "$output" == *"theme dir"* ]]
}

# ===========================================================================
# T013 — GNOME absent → unsupported
# ===========================================================================

@test "gnome-theme-bundle: exits non-zero when GNOME absent" {
  base_gnome_present_off
  run _run_theme_install
  [ "$status" -ne 0 ]
}

@test "gnome-theme-bundle: names unsupported when GNOME absent" {
  base_gnome_present_off
  run _run_theme_install
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome-theme-bundle: does not call gext when GNOME absent" {
  base_gnome_present_off
  run _run_theme_install
  [ ! -s "${STUB_GEXT_LOG}" ]
}

@test "gnome-theme-bundle: does not call git when GNOME absent" {
  base_gnome_present_off
  run _run_theme_install
  [ ! -s "${STUB_GIT_LOG}" ]
}

# ===========================================================================
# T013 — idempotency
# ===========================================================================

@test "gnome-theme-bundle: re-run exits 0 (idempotent)" {
  _run_theme_install >/dev/null 2>&1
  run _run_theme_install
  [ "$status" -eq 0 ]
}

@test "gnome-theme-bundle: User Themes UUID appears exactly once after double run" {
  _run_theme_install >/dev/null 2>&1
  _run_theme_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${_USER_THEMES_UUID}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}
