load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Hermetic-PATH tool set: a minimal real-tool farm with NO `fresh`, used to
# exercise the laravel-lsp editor-missing edge.
_CLEAN_TOOLS="bash sh env printf mktemp grep sed awk head tail cut tr cat ls dirname \
basename chmod mkdir mv cp rm ln sort uniq wc find xargs sleep test touch tee readlink \
realpath uname id python3 jq"

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export FRESH_CONFIG="${HOME}/.config/fresh/config.json"

  # Scratch yum.repos.d so the ddev module needs no root and never touches /etc.
  export DEVBOOST_YUM_REPOS_DIR="${BATS_TEST_TMPDIR}/yum.repos.d"
  mkdir -p "${DEVBOOST_YUM_REPOS_DIR}"

  # Happy-path: ensure `fresh` is present for laravel-lsp wiring.
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fresh"
  chmod +x "$(base_stub_dir)/fresh"

  # Clean farm (no `fresh`) for the editor-missing test.
  _clean_bin="$(mktemp -d)"
  local c src
  for c in ${_CLEAN_TOOLS}; do
    src="$(command -v "${c}" 2>/dev/null)" && ln -sf "${src}" "${_clean_bin}/${c}"
  done
  ln -sf "$(base_stub_dir)/mise" "${_clean_bin}/mise"
}

teardown() {
  [[ -n "${_clean_bin:-}" && -d "${_clean_bin}" ]] && rm -rf "${_clean_bin}"
  base_teardown
}

# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
_run_ddev() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export DEVBOOST_YUM_REPOS_DIR='${DEVBOOST_YUM_REPOS_DIR}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_DDEV_LOG='${STUB_DDEV_LOG}'
    bash '${DEVBOOST_ROOT}/modules/ddev/install.sh'
  " 2>&1
}

# Hermetic ddev runner: PATH = stub dir + clean-tool farm only, so a real
# /usr/bin/ddev on the host cannot leak in and satisfy `have ddev` prematurely.
# (The ddev stub itself must be removed by the caller via base_remove_ddev.)
_run_ddev_hermetic() {
  bash -c "
    export HOME='${HOME}'
    export PATH='$(base_stub_dir):${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export DEVBOOST_YUM_REPOS_DIR='${DEVBOOST_YUM_REPOS_DIR}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_DDEV_LOG='${STUB_DDEV_LOG}'
    bash '${DEVBOOST_ROOT}/modules/ddev/install.sh'
  " 2>&1
}

_run_laravel_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/laravel-lsp/install.sh'
  " 2>&1
}

_run_laravel_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/laravel-lsp/install.sh'
  " 2>&1
}

_run_verify_laravel_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/laravel-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# ddev module
# ===========================================================================

@test "ddev: writes ddev.repo into DEVBOOST_YUM_REPOS_DIR with pkg.ddev.com baseurl" {
  base_remove_ddev   # force the full install path (skip-if-present is covered separately)
  run _run_ddev_hermetic
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_YUM_REPOS_DIR}/ddev.repo" ]
  grep -q '\[ddev\]' "${DEVBOOST_YUM_REPOS_DIR}/ddev.repo"
  grep -q 'baseurl=https://pkg.ddev.com/yum/' "${DEVBOOST_YUM_REPOS_DIR}/ddev.repo"
}

@test "ddev: installs ddev via dnf --refresh" {
  base_remove_ddev   # force the full install path
  run _run_ddev_hermetic
  [ "$status" -eq 0 ]
  grep -q 'install --refresh -y ddev' "${STUB_DNF_LOG}"
}

@test "ddev: command -v ddev resolves (verify clause) when ddev is present" {
  # ddev stub is on PATH (base_setup) → the module's verify command is satisfied.
  command -v ddev >/dev/null 2>&1
  run bash -c "command -v ddev >/dev/null 2>&1"
  [ "$status" -eq 0 ]
}

@test "ddev: installs NO host php/composer" {
  base_remove_ddev   # force the full install path so the dnf log reflects real intent
  run _run_ddev_hermetic
  [ "$status" -eq 0 ]
  grep -q 'install --refresh -y ddev' "${STUB_DNF_LOG}"   # the install DID run
  ! grep -qi 'php' "${STUB_DNF_LOG}"
  ! grep -qi 'composer' "${STUB_DNF_LOG}"
}

@test "ddev: idempotent — pre-existing ddev.repo is not rewritten and no error" {
  base_remove_ddev   # reach the repo-write step (skip-if-present is covered separately)
  printf '[ddev]\nname=ddev\nbaseurl=https://pkg.ddev.com/yum/\ngpgcheck=0\nenabled=1\n# sentinel\n' \
    > "${DEVBOOST_YUM_REPOS_DIR}/ddev.repo"
  run _run_ddev_hermetic
  [ "$status" -eq 0 ]
  grep -q '# sentinel' "${DEVBOOST_YUM_REPOS_DIR}/ddev.repo"   # pre-existing repo untouched
}

@test "ddev: idempotent re-run when ddev already present (skip-if have ddev)" {
  # ddev stub is already on PATH (base_setup), so the module should short-circuit.
  run _run_ddev
  [ "$status" -eq 0 ]
}

# ===========================================================================
# laravel-lsp module
# ===========================================================================

@test "laravel-lsp: provisions intelephense via mise and enables lsp.php" {
  run _run_laravel_lsp
  [ "$status" -eq 0 ]
  grep -q 'use -g npm:intelephense@' "${STUB_MISE_LOG}"
  [ "$(jq -r '.lsp.php.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.php.args | join(" ")' "${FRESH_CONFIG}")" = "--stdio" ]
  [ "$(jq -r '.lsp.php.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/intelephense" ]
}

@test "laravel-lsp: seeds base config when absent (theme preserved on merge)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_laravel_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
}

@test "laravel-lsp: verify GREEN after provisioning" {
  _run_laravel_lsp >/dev/null
  run _run_verify_laravel_lsp
  [ "$status" -eq 0 ]
}

@test "laravel-lsp: verify RED before provisioning" {
  run _run_verify_laravel_lsp
  [ "$status" -ne 0 ]
}

@test "laravel-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_laravel_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_laravel_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

@test "laravel-lsp: fresh missing — module fails NAMING the editor" {
  run _run_laravel_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

# ===========================================================================
# templates/laravel
# ===========================================================================

@test "templates/laravel/.fresh/config.json is valid JSON, tab_size 4, PHP formatter = vendor/bin/pint" {
  local cfg="${DEVBOOST_ROOT}/templates/laravel/.fresh/config.json"
  [ -f "${cfg}" ]
  jq -e . "${cfg}" >/dev/null
  [ "$(jq -r '.editor.tab_size' "${cfg}")" = "4" ]
  jq -r '.. | strings' "${cfg}" | grep -q 'vendor/bin/pint'
}

@test "templates/laravel/README.md documents the ddev Laravel flow" {
  local readme="${DEVBOOST_ROOT}/templates/laravel/README.md"
  [ -f "${readme}" ]
  grep -q 'project-type=laravel' "${readme}"
  grep -q 'docroot=public' "${readme}"
  grep -q 'ddev composer create laravel/laravel' "${readme}"
  grep -q 'ddev start' "${readme}"
}

# ===========================================================================
# Unsupported-OS gating (engine-driven)
# ===========================================================================

@test "ddev: unsupported-OS — engine reports failure on non-fedora" {
  base_remove_ddev   # so the verify guard does not short-circuit before the OS gate
  # Hermetic PATH (stub dir + clean farm, no ddev anywhere) so a real /usr/bin/ddev
  # cannot satisfy the verify clause and skip the module before the OS gate.
  # Non-strict (like the fresh-lsp suite): the engine processes the whole graph and
  # summary_print returns non-zero because ddev has no fedora-only install command on
  # ubuntu → it is recorded as \"unsupported\".
  run bash -c "
    export HOME='${HOME}'
    export PATH='$(base_stub_dir):${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- ddev
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

@test "laravel-lsp: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- laravel-lsp
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}


