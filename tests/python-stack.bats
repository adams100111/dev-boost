load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Hermetic clean-PATH farm used for the fresh-missing case so a real host `fresh`
# (or a stub from a prior test) cannot leak into the python-lsp install.
_CLEAN_TOOLS="bash sh env printf mktemp grep sed awk head tail cut tr cat ls dirname \
basename chmod mkdir mv cp rm ln sort uniq wc find xargs sleep test touch tee readlink \
realpath uname id python3 jq"

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export FRESH_CONFIG="${HOME}/.config/fresh/config.json"
  # Happy-path: ensure `fresh` is present (deterministic on hosts with/without a real fresh).
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fresh"
  chmod +x "$(base_stub_dir)/fresh"
  # Clean farm (no `fresh`) for the fresh-missing test.
  _clean_bin="$(mktemp -d)"
  local c src
  for c in ${_CLEAN_TOOLS}; do
    src="$(command -v "${c}" 2>/dev/null)" && ln -sf "${src}" "${_clean_bin}/${c}"
  done
  ln -sf "$(base_stub_dir)/mise" "${_clean_bin}/mise"
  # Stub curl (uv installer simulation) — NOT the host curl — so the uv install path
  # is hermetic and a real host `uv`/network cannot leak.
  ln -sf "$(base_stub_dir)/curl" "${_clean_bin}/curl"
}

teardown() {
  [[ -n "${_clean_bin:-}" && -d "${_clean_bin}" ]] && rm -rf "${_clean_bin}"
  base_teardown
}

# --- uv -----------------------------------------------------------------------

# Run uv/install.sh on the hermetic clean PATH (no host `uv`; stub curl) so the
# install path is deterministic regardless of whether the host has a real uv.
_run_uv() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_UV_LOG='${STUB_UV_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    bash '${DEVBOOST_ROOT}/modules/uv/install.sh'
  " 2>&1
}

# Engine install on the hermetic clean PATH (no host `uv`) so the OS gate is
# reached instead of being masked by a host-present uv satisfying verify.
_engine_install_uv_clean() {
  local distro="${1:-fedora}" family="${2:-fedora}"
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${distro}'
    export OS_FAMILY='${family}'
    export STUB_UV_LOG='${STUB_UV_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- uv
  " 2>&1
}

# --- python-lsp ---------------------------------------------------------------

_run_python_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/python-lsp/install.sh'
  " 2>&1
}

_run_python_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/python-lsp/install.sh'
  " 2>&1
}

_run_verify_python_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/python-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# uv
# ===========================================================================

@test "uv: install attempts the pinned astral installer URL" {
  run _run_uv
  [ "$status" -eq 0 ]
  # The pinned URL must appear in either the curl log or the dedicated uv log.
  grep -q 'astral.sh/uv/0.11.23/install.sh' "${STUB_UV_LOG}" "${STUB_CURL_LOG}"
}

@test "uv: uv binary resolves after install" {
  run _run_uv
  [ "$status" -eq 0 ]
  # The stub curl|sh installer drops a `uv` binary into the (clean) PATH dir.
  PATH="${_clean_bin}" command -v uv >/dev/null 2>&1
}

@test "uv: idempotent — re-run when uv already present is a no-op skip" {
  _run_uv >/dev/null
  : > "${STUB_UV_LOG}"
  run _run_uv
  [ "$status" -eq 0 ]
  # Second run should not re-attempt the installer (uv already present).
  [ ! -s "${STUB_UV_LOG}" ]
}

@test "uv: module [install] only targets fedora" {
  run _module_install_cmd uv fedora fedora
  [ "$status" -eq 0 ]
  [[ "$output" == *"modules/uv/install.sh"* ]]
}

@test "uv: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install_uv_clean ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# python-lsp
# ===========================================================================

@test "python-lsp: provisions both servers via mise with pinned specs" {
  run _run_python_lsp
  [ "$status" -eq 0 ]
  grep -q 'use -g pipx:basedpyright@1.39.8' "${STUB_MISE_LOG}"
  grep -q 'use -g pipx:ruff@0.15.18' "${STUB_MISE_LOG}"
}

@test "python-lsp: wires lsp.python + lsp.pythonfmt (enabled, absolute command)" {
  run _run_python_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.lsp.python.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.python.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/basedpyright-langserver" ]
  [ "$(jq -r '.lsp.python.args | join(" ")' "${FRESH_CONFIG}")" = "--stdio" ]
  [ "$(jq -r '.lsp.pythonfmt.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.pythonfmt.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/ruff" ]
  [ "$(jq -r '.lsp.pythonfmt.args | join(" ")' "${FRESH_CONFIG}")" = "server" ]
}

@test "python-lsp: seeds base config when absent (preserves base keys)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_python_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
  [ "$(jq -r '.editor.format_on_save' "${FRESH_CONFIG}")" = "true" ]
}

@test "python-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_python_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_python_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

@test "python-lsp: fresh missing — module fails NAMING the editor" {
  run _run_python_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

@test "python-lsp: verify GREEN after provisioning" {
  _run_python_lsp >/dev/null
  run _run_verify_python_lsp
  [ "$status" -eq 0 ]
}

@test "python-lsp: verify RED before provisioning (no config)" {
  run _run_verify_python_lsp
  [ "$status" -ne 0 ]
}

@test "python-lsp: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install python-lsp ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# templates/python
# ===========================================================================

@test "templates/python: .fresh/config.json present with tab_size 4" {
  local cfg="${DEVBOOST_ROOT}/templates/python/.fresh/config.json"
  [ -f "${cfg}" ]
  [ "$(jq -r '.editor.tab_size' "${cfg}")" = "4" ]
}

@test "templates/python: pyproject.toml + README.md present" {
  [ -f "${DEVBOOST_ROOT}/templates/python/pyproject.toml" ]
  [ -f "${DEVBOOST_ROOT}/templates/python/README.md" ]
  grep -q '\[tool.ruff\]' "${DEVBOOST_ROOT}/templates/python/pyproject.toml"
}
