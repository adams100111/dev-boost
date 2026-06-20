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

# The 6 pinned functional UUIDs (spec §D5 / contracts/gnome-extensions.md)
_FUNCTIONAL_UUIDS=(
  "appindicatorsupport@rgcjonas.gmail.com"
  "clipboard-indicator@tudmotu.com"
  "caffeine@patapon.info"
  "gsconnect@andyholmes.github.io"
  "dash-to-dock@micxgx.gmail.com"
  "emoji-copy@felipeftn"
)

# ---------------------------------------------------------------------------
# Helper: run modules/gnome-extensions/install.sh in a subshell.
# ---------------------------------------------------------------------------
_run_gnome_extensions_install() {
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
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    bash '${DEVBOOST_ROOT}/modules/gnome-extensions/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: run modules/gnome-extensions/install.sh --verify-only in a subshell.
# This invokes the REAL verify command shipped in module.toml.
# ---------------------------------------------------------------------------
_run_gnome_extensions_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-GNOME}'
    export STUB_GNOME_PRESENT='${STUB_GNOME_PRESENT:-1}'
    export STUB_GNOME_SHELL_VERSION='${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}'
    export STUB_GEXT_LOG='${STUB_GEXT_LOG}'
    export STUB_GEXT_MISMATCH_UUID='${STUB_GEXT_MISMATCH_UUID:-}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    export STUB_DCONF_LOG='${STUB_DCONF_LOG}'
    export STUB_DCONF_STATE_FILE='${STUB_DCONF_STATE_FILE}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    bash '${DEVBOOST_ROOT}/modules/gnome-extensions/install.sh' --verify-only
  " 2>&1
}

# ===========================================================================
# T009 — module shape
# ===========================================================================

@test "gnome-extensions: modules/gnome-extensions/module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-extensions/module.toml" ]
}

@test "gnome-extensions: modules/gnome-extensions/install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gnome-extensions/install.sh" ]
}

@test "gnome-extensions: module.toml category is gnome" {
  grep -q 'category.*=.*"gnome"' "${DEVBOOST_ROOT}/modules/gnome-extensions/module.toml"
}

@test "gnome-extensions: module.toml requires gnome-settings" {
  grep -q 'gnome-settings' "${DEVBOOST_ROOT}/modules/gnome-extensions/module.toml"
}

@test "gnome-extensions: module.toml install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/gnome-extensions/module.toml"
}

# ===========================================================================
# T009 — gext install called for each functional UUID
# ===========================================================================

@test "gnome-extensions: gext install attempted for appindicatorsupport@rgcjonas.gmail.com" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install appindicatorsupport@rgcjonas.gmail.com' "${STUB_GEXT_LOG}"
}

@test "gnome-extensions: gext install attempted for clipboard-indicator@tudmotu.com" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install clipboard-indicator@tudmotu.com' "${STUB_GEXT_LOG}"
}

@test "gnome-extensions: gext install attempted for caffeine@patapon.info" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install caffeine@patapon.info' "${STUB_GEXT_LOG}"
}

@test "gnome-extensions: gext install attempted for gsconnect@andyholmes.github.io" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install gsconnect@andyholmes.github.io' "${STUB_GEXT_LOG}"
}

@test "gnome-extensions: gext install attempted for dash-to-dock@micxgx.gmail.com" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install dash-to-dock@micxgx.gmail.com' "${STUB_GEXT_LOG}"
}

@test "gnome-extensions: gext install attempted for emoji-copy@felipeftn" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  grep -qF 'gext install emoji-copy@felipeftn' "${STUB_GEXT_LOG}"
}

# ===========================================================================
# T009 — author-verify: passes when metadata uuid matches each pinned UUID
# ===========================================================================

@test "gnome-extensions: author-verify passes for all 6 UUIDs (stub writes matching metadata)" {
  # The gext stub writes metadata.json with the requested UUID by default;
  # a successful install run (status=0) proves all verifies passed.
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T009 — author-verify: INJECTED mismatch → named failure
# The mismatch test uses a fresh HOME (no pre-existing ext dir) so the
# STUB_GEXT_MISMATCH_UUID knob takes effect.
# ===========================================================================

@test "gnome-extensions: author-verify mismatch causes named failure (non-zero exit)" {
  # Inject a bad uuid so metadata.json will have a UUID that doesn't match the pinned one.
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_gnome_extensions_install
  [ "$status" -ne 0 ]
}

@test "gnome-extensions: author-verify mismatch names the failure (mismatch/author in output)" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_gnome_extensions_install
  [[ "$output" == *"mismatch"* ]] || [[ "$output" == *"author"* ]] || [[ "$output" == *"verify"* ]]
}

@test "gnome-extensions: author-verify mismatch names the UUID in the error" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_gnome_extensions_install
  # Output should contain one of the pinned UUIDs (the first one attempted will fail)
  [[ "$output" == *"appindicatorsupport@rgcjonas.gmail.com"* ]]
}

@test "gnome-extensions: author-verify mismatch does NOT enable the mismatched UUID" {
  export STUB_GEXT_MISMATCH_UUID="evil@attacker.example"
  run _run_gnome_extensions_install
  # Independent assertion 1: the module must have failed.
  [ "$status" -ne 0 ]
  # Independent assertion 2: the first pinned UUID must genuinely be absent from
  # enabled-extensions (the install aborted before any enable could happen).
  ! grep -qF 'appindicatorsupport@rgcjonas.gmail.com' "${STUB_GSETTINGS_STATE_FILE}"
}

# ===========================================================================
# T009 — enable dedup: each UUID added exactly once even after double run
# ===========================================================================

@test "gnome-extensions: appindicatorsupport@rgcjonas.gmail.com appears exactly once after double run" {
  local uuid="appindicatorsupport@rgcjonas.gmail.com"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-extensions: clipboard-indicator@tudmotu.com appears exactly once after double run" {
  local uuid="clipboard-indicator@tudmotu.com"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-extensions: caffeine@patapon.info appears exactly once after double run" {
  local uuid="caffeine@patapon.info"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-extensions: gsconnect@andyholmes.github.io appears exactly once after double run" {
  local uuid="gsconnect@andyholmes.github.io"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-extensions: dash-to-dock@micxgx.gmail.com appears exactly once after double run" {
  local uuid="dash-to-dock@micxgx.gmail.com"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

@test "gnome-extensions: emoji-copy@felipeftn appears exactly once after double run" {
  local uuid="emoji-copy@felipeftn"
  _run_gnome_extensions_install >/dev/null 2>&1
  _run_gnome_extensions_install >/dev/null 2>&1
  local count
  count="$(grep -oF "${uuid}" "${STUB_GSETTINGS_STATE_FILE}" | wc -l)"
  [ "${count}" -eq 1 ]
}

# ===========================================================================
# T009 — verify: RED before install, GREEN after
# ===========================================================================

@test "gnome-extensions: verify is RED before install (no ext dirs, no enabled list)" {
  # Nothing installed yet — verify must fail
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export STUB_GSETTINGS_STATE_FILE='${STUB_GSETTINGS_STATE_FILE}'
    enabled=\$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || echo '@as []')
    [[ \"\${enabled}\" == *'appindicatorsupport@rgcjonas.gmail.com'* ]]
  " 2>&1
  [ "$status" -ne 0 ]
}

@test "gnome-extensions: verify is RED before install (ext dir absent)" {
  local uuid="appindicatorsupport@rgcjonas.gmail.com"
  [ ! -d "${HOME}/.local/share/gnome-shell/extensions/${uuid}" ]
}

@test "gnome-extensions: verify is GREEN after install — all 6 ext dirs present" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  for uuid in "${_FUNCTIONAL_UUIDS[@]}"; do
    [ -d "${HOME}/.local/share/gnome-shell/extensions/${uuid}" ]
  done
}

@test "gnome-extensions: verify is GREEN after install — all 6 UUIDs in enabled-extensions" {
  run _run_gnome_extensions_install
  [ "$status" -eq 0 ]
  local enabled
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  for uuid in "${_FUNCTIONAL_UUIDS[@]}"; do
    [[ "${enabled}" == *"${uuid}"* ]]
  done
}

# ===========================================================================
# T009 — real --verify-only command: RED before install, GREEN after
# These exercise the actual verify path shipped in module.toml.
# ===========================================================================

@test "gnome-extensions: --verify-only exits non-zero in pristine scratch HOME (no extensions installed)" {
  # Nothing has been installed; the real --verify-only must fail.
  run _run_gnome_extensions_verify
  [ "$status" -ne 0 ]
}

@test "gnome-extensions: --verify-only exits 0 after a successful install" {
  # Install first, then verify with the real --verify-only flag.
  _run_gnome_extensions_install >/dev/null 2>&1
  run _run_gnome_extensions_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T009 — GNOME absent → unsupported failure
# ===========================================================================

@test "gnome-extensions: exits non-zero when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_extensions_install
  [ "$status" -ne 0 ]
}

@test "gnome-extensions: names 'unsupported' when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_extensions_install
  [[ "$output" == *"unsupported"* ]]
}

@test "gnome-extensions: does not call gext when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_extensions_install
  [ ! -s "${STUB_GEXT_LOG}" ]
}

@test "gnome-extensions: does not modify enabled-extensions when GNOME is absent" {
  base_gnome_present_off
  run _run_gnome_extensions_install
  [ ! -s "${STUB_GSETTINGS_STATE_FILE}" ]
}
