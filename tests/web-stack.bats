load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

_CLEAN_TOOLS="bash sh env printf mktemp grep sed awk head tail cut tr cat ls dirname \
basename chmod mkdir mv cp rm ln sort uniq wc find xargs sleep test touch tee readlink \
realpath uname id python3 jq"

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export FRESH_CONFIG="${HOME}/.config/fresh/config.json"
  # Happy-path: ensure `fresh` is present.
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

# --- web-runtimes ----------------------------------------------------------

_run_runtimes() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/web-runtimes/install.sh'
  " 2>&1
}

_run_verify_runtimes() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/web-runtimes/verify.sh'
  " 2>&1
}

# --- web-lsp ---------------------------------------------------------------

_run_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/web-lsp/install.sh'
  " 2>&1
}

_run_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/web-lsp/install.sh'
  " 2>&1
}

_run_verify_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/web-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# web-runtimes
# ===========================================================================

@test "web-runtimes: installs node/pnpm/bun via a single pinned mise use line" {
  run _run_runtimes
  [ "$status" -eq 0 ]
  grep -q 'use -g node@22 pnpm@11.8.0 bun@1.3.14' "${STUB_MISE_LOG}"
  # one combined line (not three separate `mise use` calls).
  [ "$(grep -c 'use -g node' "${STUB_MISE_LOG}")" = "1" ]
}

@test "web-runtimes: verify GREEN after install (node/pnpm/bun resolve)" {
  _run_runtimes >/dev/null
  run _run_verify_runtimes
  [ "$status" -eq 0 ]
}

@test "web-runtimes: verify RED when a runtime cannot be resolved" {
  export STUB_MISE_WHICH_FAIL="bun"
  run _run_verify_runtimes
  [ "$status" -ne 0 ]
}

@test "web-runtimes: idempotent — re-run is stable and still GREEN" {
  _run_runtimes >/dev/null
  run _run_runtimes
  [ "$status" -eq 0 ]
  run _run_verify_runtimes
  [ "$status" -eq 0 ]
}

@test "web-runtimes: module.toml is fedora-only (no other [install] keys)" {
  local keys
  keys="$(grep -A20 '^\[install\]' "${DEVBOOST_ROOT}/modules/web-runtimes/module.toml" \
    | grep -oE '^[a-z_]+[[:space:]]*=' | sed 's/[[:space:]]*=//' | sort -u | tr '\n' ',')"
  [ "${keys}" = "fedora," ]
}

# ===========================================================================
# web-lsp
# ===========================================================================

@test "web-lsp: provisions all four servers via pinned mise specs" {
  run _run_lsp
  [ "$status" -eq 0 ]
  grep -q 'use -g npm:typescript-language-server@5.3.0' "${STUB_MISE_LOG}"
  grep -q 'use -g npm:vscode-langservers-extracted@4.10.0' "${STUB_MISE_LOG}"
  grep -q 'use -g npm:@tailwindcss/language-server@0.14.29' "${STUB_MISE_LOG}"
  grep -q 'use -g npm:prettier@3.8.4' "${STUB_MISE_LOG}"
}

@test "web-lsp: wires each lsp entry enabled with absolute mise command" {
  run _run_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.lsp.typescript.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.eslint.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.tailwindcss.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.prettier.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.typescript.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/typescript-language-server" ]
  [ "$(jq -r '.lsp.typescript.args | join(" ")' "${FRESH_CONFIG}")" = "--stdio" ]
  # prettier has no args.
  [ "$(jq -r '.lsp.prettier.args | length' "${FRESH_CONFIG}")" = "0" ]
}

@test "web-lsp: seeds base config when absent (theme preserved)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
}

@test "web-lsp: jq-merge preserves a pre-existing custom key" {
  mkdir -p "$(dirname "${FRESH_CONFIG}")"
  printf '{ "version":1, "theme":"my-theme", "custom":"keep-me", "lsp":{} }\n' > "${FRESH_CONFIG}"
  run _run_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.custom' "${FRESH_CONFIG}")" = "keep-me" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "my-theme" ]
}

@test "web-lsp: verify GREEN after provisioning" {
  _run_lsp >/dev/null
  run _run_verify_lsp
  [ "$status" -eq 0 ]
}

@test "web-lsp: verify RED before provisioning (no config)" {
  run _run_verify_lsp
  [ "$status" -ne 0 ]
}

@test "web-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

@test "web-lsp: fresh missing — module fails NAMING the editor" {
  run _run_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

@test "web-lsp: module.toml is fedora-only (no other [install] keys)" {
  local keys
  keys="$(grep -A20 '^\[install\]' "${DEVBOOST_ROOT}/modules/web-lsp/module.toml" \
    | grep -oE '^[a-z_]+[[:space:]]*=' | sed 's/[[:space:]]*=//' | sort -u | tr '\n' ',')"
  [ "${keys}" = "fedora," ]
}

# ===========================================================================
# templates/nextjs
# ===========================================================================

@test "templates/nextjs/.fresh/config.json: present, valid JSON, tab_size 2" {
  local f="${DEVBOOST_ROOT}/templates/nextjs/.fresh/config.json"
  [ -f "${f}" ]
  jq -e . "${f}" >/dev/null
  [ "$(jq -r '.editor.tab_size' "${f}")" = "2" ]
  [ "$(jq -r '.format.command' "${f}")" = "prettier" ]
}

@test "templates/nextjs/README.md: present and mentions create flow" {
  local f="${DEVBOOST_ROOT}/templates/nextjs/README.md"
  [ -f "${f}" ]
  grep -qi 'create' "${f}"
}
