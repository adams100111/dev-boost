load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Hermetic clean-PATH farm used for the fresh-missing case so a real host `fresh`
# (or a stub from a prior test) cannot leak into the devops-lsp install.
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
}

teardown() {
  [[ -n "${_clean_bin:-}" && -d "${_clean_bin}" ]] && rm -rf "${_clean_bin}"
  base_teardown
}

# --- devops-tools -------------------------------------------------------------

_run_devops_tools() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/devops-tools/install.sh'
  " 2>&1
}

_run_verify_devops_tools() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/devops-tools/verify.sh'
  " 2>&1
}

# --- devops-lsp ---------------------------------------------------------------

_run_devops_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_MISE_WHICH_FAIL='${STUB_MISE_WHICH_FAIL:-}'
    bash '${DEVBOOST_ROOT}/modules/devops-lsp/install.sh'
  " 2>&1
}

_run_devops_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    bash '${DEVBOOST_ROOT}/modules/devops-lsp/install.sh'
  " 2>&1
}

_run_verify_devops_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/devops-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# devops-tools
# ===========================================================================

@test "devops-tools: provisions the four tools in one pinned mise declaration" {
  run _run_devops_tools
  [ "$status" -eq 0 ]
  grep -q 'use -g .*aqua:opentofu/opentofu@1.11.6' "${STUB_MISE_LOG}"
  grep -q 'use -g .*aqua:kubernetes/kubectl@1.35.2' "${STUB_MISE_LOG}"
  grep -q 'use -g .*aqua:helm/helm@4.1.4' "${STUB_MISE_LOG}"
  grep -q 'use -g .*aqua:derailed/k9s@0.51.0' "${STUB_MISE_LOG}"
  # All four pins on a single `use -g` line.
  [ "$(grep -c 'use -g ' "${STUB_MISE_LOG}")" -eq 1 ]
}

@test "devops-tools: verify GREEN after provisioning (tofu/kubectl/helm/k9s resolve)" {
  _run_devops_tools >/dev/null
  run _run_verify_devops_tools
  [ "$status" -eq 0 ]
}

@test "devops-tools: verify RED when a tool cannot be resolved via mise" {
  export STUB_MISE_WHICH_FAIL="tofu"
  run _run_verify_devops_tools
  [ "$status" -ne 0 ]
}

@test "devops-tools: idempotent — re-run re-issues the same single pinned declaration" {
  _run_devops_tools >/dev/null
  : > "${STUB_MISE_LOG}"
  run _run_devops_tools
  [ "$status" -eq 0 ]
  [ "$(grep -c 'use -g ' "${STUB_MISE_LOG}")" -eq 1 ]
  grep -q 'aqua:opentofu/opentofu@1.11.6' "${STUB_MISE_LOG}"
}

@test "devops-tools: module [install] only targets fedora" {
  run _module_install_cmd devops-tools fedora fedora
  [ "$status" -eq 0 ]
  [[ "$output" == *"modules/devops-tools/install.sh"* ]]
}

@test "devops-tools: unsupported-OS — engine reports failure on non-fedora" {
  # Force verify RED so the engine cannot pre-skip the module as already-installed
  # (its `mise which` verify is otherwise GREEN under the stub harness on any OS);
  # the engine then reaches the missing-install-command gate and fails as unsupported.
  export STUB_MISE_WHICH_FAIL="tofu kubectl helm k9s"
  run _engine_install devops-tools ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# devops-lsp
# ===========================================================================

@test "devops-lsp: provisions tofu-ls via mise with the pinned spec" {
  run _run_devops_lsp
  [ "$status" -eq 0 ]
  grep -q 'use -g aqua:opentofu/tofu-ls@0.0.22' "${STUB_MISE_LOG}"
}

@test "devops-lsp: wires lsp.terraform (enabled, absolute command, args)" {
  run _run_devops_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.lsp.terraform.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.terraform.command' "${FRESH_CONFIG}")" = "${HOME}/.local/share/mise/shims/tofu-ls" ]
  [ "$(jq -r '.lsp.terraform.args | join(" ")' "${FRESH_CONFIG}")" = "serve" ]
}

@test "devops-lsp: seeds base config when absent (preserves base keys)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_devops_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
  [ "$(jq -r '.editor.format_on_save' "${FRESH_CONFIG}")" = "true" ]
}

@test "devops-lsp: jq-merge preserves a pre-existing custom key" {
  mkdir -p "$(dirname "${FRESH_CONFIG}")"
  printf '{ "version":1, "theme":"my-theme", "custom":"keep-me", "lsp":{} }\n' > "${FRESH_CONFIG}"
  run _run_devops_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.custom' "${FRESH_CONFIG}")" = "keep-me" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "my-theme" ]
  [ "$(jq -r '.lsp.terraform.enabled' "${FRESH_CONFIG}")" = "true" ]
}

@test "devops-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_devops_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_devops_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

@test "devops-lsp: fresh missing — module fails NAMING the editor" {
  run _run_devops_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

@test "devops-lsp: verify GREEN after provisioning" {
  _run_devops_lsp >/dev/null
  run _run_verify_devops_lsp
  [ "$status" -eq 0 ]
}

@test "devops-lsp: verify RED before provisioning (no config)" {
  run _run_verify_devops_lsp
  [ "$status" -ne 0 ]
}

@test "devops-lsp: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install devops-lsp ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
