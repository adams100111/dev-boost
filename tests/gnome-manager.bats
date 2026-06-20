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
# Helpers: run gnome-manager-apps install/verify in a subshell.
# ---------------------------------------------------------------------------
_run_manager_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_FLATPAK_LOG='${STUB_FLATPAK_LOG}'
    export STUB_FLATPAK_REMOTES='${STUB_FLATPAK_REMOTES:-}'
    export STUB_FLATPAK_INSTALLED='${STUB_FLATPAK_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/gnome-manager-apps/install.sh'
  " 2>&1
}

_run_manager_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_FLATPAK_LOG='${STUB_FLATPAK_LOG}'
    export STUB_FLATPAK_INSTALLED='${STUB_FLATPAK_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/gnome-manager-apps/install.sh' --verify-only
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helpers: run gnome-aesthetics-bundle install/verify in a subshell.
# ---------------------------------------------------------------------------
_AESTHETICS_UUIDS=(
  "blur-my-shell@aunetx"
  "just-perfection-desktop@just-perfection"
  "vertical-workspaces@G-dH.github.com"
  "monitor@astraext.github.io"
  "CoverflowAltTab@palatis.blogspot.com"
)

_run_aesthetics_install() {
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
    bash '${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/install.sh'
  " 2>&1
}

_run_aesthetics_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    bash '${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/install.sh' --verify-only
  " 2>&1
}

# ===========================================================================
# T011 — module shape: gnome-manager-apps
# ===========================================================================

@test "gnome-manager-apps: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-manager-apps/module.toml" ]
}

@test "gnome-manager-apps: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-manager-apps/install.sh" ]
}

@test "gnome-manager-apps: module.toml category is gnome" {
  grep -q 'category.*=.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-manager-apps/module.toml"
}

@test "gnome-manager-apps: module.toml requires gnome-settings" {
  grep -q 'gnome-settings' "${DEVBOOST_ROOT}/modules/gnome-manager-apps/module.toml"
}

@test "gnome-manager-apps: module.toml profiles includes gnome" {
  grep -q '"gnome"' "${DEVBOOST_ROOT}/modules/gnome-manager-apps/module.toml"
}

@test "gnome-manager-apps: module.toml install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/gnome-manager-apps/module.toml"
}

# ===========================================================================
# T011 — install: apps installed
# ===========================================================================

@test "gnome-manager-apps: install exits 0 on GNOME system" {
  run _run_manager_install
  [ "$status" -eq 0 ]
}

@test "gnome-manager-apps: installs gnome-extensions-app via dnf" {
  run _run_manager_install
  [ "$status" -eq 0 ]
  grep -qF 'gnome-extensions-app' "${STUB_DNF_LOG}"
}

@test "gnome-manager-apps: installs gnome-tweaks via dnf" {
  run _run_manager_install
  [ "$status" -eq 0 ]
  grep -qF 'gnome-tweaks' "${STUB_DNF_LOG}"
}

@test "gnome-manager-apps: adds flathub remote" {
  run _run_manager_install
  [ "$status" -eq 0 ]
  grep -qF 'flathub' "${STUB_FLATPAK_LOG}"
}

@test "gnome-manager-apps: installs Extension Manager flatpak" {
  run _run_manager_install
  [ "$status" -eq 0 ]
  grep -qF 'com.mattjakeman.ExtensionManager' "${STUB_FLATPAK_LOG}"
}

@test "gnome-manager-apps: skips Extension Manager install when already listed" {
  export STUB_FLATPAK_INSTALLED="com.mattjakeman.ExtensionManager"
  run _run_manager_install
  [ "$status" -eq 0 ]
  # flatpak install should NOT have been called
  ! grep -qF 'flatpak install' "${STUB_FLATPAK_LOG}"
}

# ===========================================================================
# T011 — verify: RED before, GREEN after
# ===========================================================================

@test "gnome-manager-apps: verify is RED before install (no apps present)" {
  run _run_manager_verify
  [ "$status" -ne 0 ]
}

@test "gnome-manager-apps: verify is GREEN after install (with apps simulated present)" {
  # Install first
  run _run_manager_install
  [ "$status" -eq 0 ]
  # Simulate apps now available: put gnome-tweaks on PATH + set flatpak installed knob
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/gnome-tweaks"
  chmod +x "$(base_stub_dir)/gnome-tweaks"
  # Put gnome-extensions on PATH to satisfy the extensions-app check
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/gnome-extensions"
  chmod +x "$(base_stub_dir)/gnome-extensions"
  export STUB_FLATPAK_INSTALLED="com.mattjakeman.ExtensionManager"
  run _run_manager_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T011 — GNOME absent → unsupported
# ===========================================================================

@test "gnome-manager-apps: exits non-zero when GNOME absent" {
  base_gnome_present_off
  run _run_manager_install
  [ "$status" -ne 0 ]
}

@test "gnome-manager-apps: names unsupported when GNOME absent" {
  base_gnome_present_off
  run _run_manager_install
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome-manager-apps: does not call dnf when GNOME absent" {
  base_gnome_present_off
  run _run_manager_install
  ! grep -qF 'gnome-tweaks' "${STUB_DNF_LOG}"
}

# ===========================================================================
# T011 — idempotency
# ===========================================================================

@test "gnome-manager-apps: re-run exits 0 (idempotent)" {
  _run_manager_install >/dev/null 2>&1
  run _run_manager_install
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T012 — module shape: gnome-aesthetics-bundle
# ===========================================================================

@test "gnome-aesthetics-bundle: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml" ]
}

@test "gnome-aesthetics-bundle: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/install.sh" ]
}

@test "gnome-aesthetics-bundle: module.toml category is gnome" {
  grep -q 'category.*=.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml"
}

@test "gnome-aesthetics-bundle: module.toml requires gnome-settings" {
  grep -q 'gnome-settings' "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml"
}

@test "gnome-aesthetics-bundle: module.toml profiles is gnome-aesthetics (NOT plain gnome)" {
  grep -q 'gnome-aesthetics' "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml"
  # profiles line must not list bare "gnome" as the sole profile
  ! grep -qE 'profiles\s*=\s*\["gnome"\]' "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml"
}

@test "gnome-aesthetics-bundle: module.toml install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/gnome-aesthetics-bundle/module.toml"
}

# ===========================================================================
# T012 — gext install called for each aesthetics UUID
# ===========================================================================

@test "gnome-aesthetics-bundle: gext install called for blur-my-shell@aunetx" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install blur-my-shell@aunetx' "${STUB_GEXT_LOG}"
}

@test "gnome-aesthetics-bundle: gext install called for just-perfection-desktop@just-perfection" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install just-perfection-desktop@just-perfection' "${STUB_GEXT_LOG}"
}

@test "gnome-aesthetics-bundle: gext install called for vertical-workspaces@G-dH.github.com" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install vertical-workspaces@G-dH.github.com' "${STUB_GEXT_LOG}"
}

@test "gnome-aesthetics-bundle: gext install called for monitor@astraext.github.io" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install monitor@astraext.github.io' "${STUB_GEXT_LOG}"
}

@test "gnome-aesthetics-bundle: gext install called for CoverflowAltTab@palatis.blogspot.com" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install CoverflowAltTab@palatis.blogspot.com' "${STUB_GEXT_LOG}"
}

# ===========================================================================
# T012 — author-verify passes for all 5 aesthetics UUIDs
# ===========================================================================

@test "gnome-aesthetics-bundle: author-verify passes for all 5 UUIDs (stub writes matching metadata)" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T012 — author-verify mismatch → named failure
# ===========================================================================

@test "gnome-aesthetics-bundle: author-verify mismatch causes non-zero exit" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_aesthetics_install
  [ "$status" -ne 0 ]
}

@test "gnome-aesthetics-bundle: author-verify mismatch names the failure in output" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_aesthetics_install
  [[ "$output" == *"mismatch"* ]] || [[ "$output" == *"author"* ]] || [[ "$output" == *"verify"* ]]
}

# ===========================================================================
# T012 — all UUIDs in enabled-extensions + dedup
# ===========================================================================

@test "gnome-aesthetics-bundle: all 5 UUIDs appear in enabled-extensions after install" {
  run _run_aesthetics_install
  [ "$status" -eq 0 ]
  local enabled
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  for uuid in "${_AESTHETICS_UUIDS[@]}"; do
    [[ "${enabled}" == *"${uuid}"* ]]
  done
}

@test "gnome-aesthetics-bundle: blur-my-shell@aunetx appears exactly once after double run" {
  local uuid="blur-my-shell@aunetx"
  _run_aesthetics_install >/dev/null 2>&1
  _run_aesthetics_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-aesthetics-bundle: CoverflowAltTab@palatis.blogspot.com appears exactly once after double run" {
  local uuid="CoverflowAltTab@palatis.blogspot.com"
  _run_aesthetics_install >/dev/null 2>&1
  _run_aesthetics_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

# ===========================================================================
# T012 — verify: RED before, GREEN after
# ===========================================================================

@test "gnome-aesthetics-bundle: --verify-only exits non-zero before install" {
  run _run_aesthetics_verify
  [ "$status" -ne 0 ]
}

@test "gnome-aesthetics-bundle: --verify-only exits 0 after install" {
  _run_aesthetics_install >/dev/null 2>&1
  run _run_aesthetics_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T012 — GNOME absent → unsupported
# ===========================================================================

@test "gnome-aesthetics-bundle: exits non-zero when GNOME absent" {
  base_gnome_present_off
  run _run_aesthetics_install
  [ "$status" -ne 0 ]
}

@test "gnome-aesthetics-bundle: names unsupported when GNOME absent" {
  base_gnome_present_off
  run _run_aesthetics_install
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome-aesthetics-bundle: does not call gext when GNOME absent" {
  base_gnome_present_off
  run _run_aesthetics_install
  [ ! -s "${STUB_GEXT_LOG}" ]
}
