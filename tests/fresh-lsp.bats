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
  # Happy-path: ensure `fresh` is present (deterministic on hosts with/without a real fresh).
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

_run_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/fresh-lsp/install.sh'
  " 2>&1
}

# Run with a hermetic PATH that has NO `fresh` (editor-missing case).
_run_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/fresh-lsp/install.sh'
  " 2>&1
}

_run_verify_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/fresh-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# Base config seed
# ===========================================================================

@test "fresh-lsp: seeds base config.json when absent (theme + format_on_save)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
  [ "$(jq -r '.editor.format_on_save' "${FRESH_CONFIG}")" = "true" ]
}

@test "fresh-lsp: never clobbers a pre-existing config (custom key preserved)" {
  mkdir -p "$(dirname "${FRESH_CONFIG}")"
  printf '{ "version":1, "theme":"my-theme", "custom":"keep-me", "lsp":{} }\n' > "${FRESH_CONFIG}"
  run _run_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.custom' "${FRESH_CONFIG}")" = "keep-me" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "my-theme" ]
}

# ===========================================================================
# Provisioning via mise + jq-merge
# ===========================================================================

@test "fresh-lsp: provisions each base server via mise and wires its lsp entry" {
  run _run_lsp
  [ "$status" -eq 0 ]
  # mise use -g called for the base specs.
  grep -q 'use -g aqua:artempyanykh/marksman' "${STUB_MISE_LOG}"
  grep -q 'use -g cargo:taplo-cli' "${STUB_MISE_LOG}"
  grep -q 'use -g npm:bash-language-server' "${STUB_MISE_LOG}"
  grep -q 'use -g npm:yaml-language-server' "${STUB_MISE_LOG}"
  # lsp entries present, enabled, command = mise shim absolute path.
  [ "$(jq -r '.lsp.markdown.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.toml.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/taplo" ]
  [ "$(jq -r '.lsp.bash.args | join(" ")' "${FRESH_CONFIG}")" = "start" ]
  [ "$(jq -r '.lsp.yaml.args | join(" ")' "${FRESH_CONFIG}")" = "--stdio" ]
}

@test "fresh-lsp: jq-merge preserves theme/editor and other keys" {
  run _run_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
  [ "$(jq -r '.editor.format_on_save' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.version' "${FRESH_CONFIG}")" = "1" ]
}

@test "fresh-lsp: scope — only the always-on base languages are wired (no stack langs)" {
  run _run_lsp
  [ "$status" -eq 0 ]
  local keys; keys="$(jq -r '.lsp | keys | sort | join(",")' "${FRESH_CONFIG}")"
  [ "${keys}" = "bash,markdown,toml,yaml" ]
  # A stack language is absent (its module belongs to dev-stacks, not editors).
  [ "$(jq -r '.lsp.python // "absent"' "${FRESH_CONFIG}")" = "absent" ]
}

@test "fresh-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

# ===========================================================================
# Verify (idempotency guard)
# ===========================================================================

@test "fresh-lsp: verify GREEN after provisioning" {
  _run_lsp >/dev/null
  run _run_verify_lsp
  [ "$status" -eq 0 ]
}

@test "fresh-lsp: verify RED before provisioning (no config)" {
  run _run_verify_lsp
  [ "$status" -ne 0 ]
}

# ===========================================================================
# Failure paths
# ===========================================================================

@test "fresh-lsp: fresh missing — module fails NAMING the editor" {
  run _run_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

@test "fresh-lsp: mise cannot resolve a tool — module fails NAMING it" {
  export STUB_MISE_WHICH_FAIL="marksman"
  run _run_lsp
  [ "$status" -ne 0 ]
  [[ "$output" == *"marksman"* ]]
}

@test "fresh-lsp: unsupported-OS — engine reports failure on non-fedora" {
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
    run_install -- fresh-lsp
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
