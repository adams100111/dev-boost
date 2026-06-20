load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Hermetic clean-PATH farm used for the fresh-missing case so a real host `fresh`
# (or a stub from a prior test) cannot leak into the dotnet-lsp install.
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
  # Clean farm (no `fresh`) for the fresh-missing test. Carry the dotnet stub so the
  # module reaches the fresh check (requires dotnet on PATH first).
  _clean_bin="$(mktemp -d)"
  local c src
  for c in ${_CLEAN_TOOLS}; do
    src="$(command -v "${c}" 2>/dev/null)" && ln -sf "${src}" "${_clean_bin}/${c}"
  done
  ln -sf "$(base_stub_dir)/dotnet" "${_clean_bin}/dotnet"
  # A real host `aspire` (e.g. ~/.aspire/bin) would otherwise leak through the
  # base stub PATH and make the install a no-op skip; run aspire on the clean farm.
}

teardown() {
  [[ -n "${_clean_bin:-}" && -d "${_clean_bin}" ]] && rm -rf "${_clean_bin}"
  base_teardown
}

# --- dotnet-sdk ---------------------------------------------------------------

_run_dotnet_sdk() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_DOTNET_LOG='${STUB_DOTNET_LOG}'
    export STUB_DOTNET_SDKS='${STUB_DOTNET_SDKS:-}'
    bash '${DEVBOOST_ROOT}/modules/dotnet-sdk/install.sh'
  " 2>&1
}

_run_verify_dotnet_sdk() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_DOTNET_LOG='${STUB_DOTNET_LOG}'
    export STUB_DOTNET_SDKS='${STUB_DOTNET_SDKS:-}'
    bash '${DEVBOOST_ROOT}/modules/dotnet-sdk/verify.sh'
  " 2>&1
}

# --- aspire -------------------------------------------------------------------

_run_aspire() {
  # Hermetic PATH (no host aspire) + the stub dir appended so `dotnet tool install`
  # can drop the freshly-created `aspire` binary where `command -v` then finds it.
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}:$(base_stub_dir)'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DOTNET_LOG='${STUB_DOTNET_LOG}'
    bash '${DEVBOOST_ROOT}/modules/aspire/install.sh'
  " 2>&1
}

# --- dotnet-lsp ---------------------------------------------------------------

_run_dotnet_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DOTNET_LOG='${STUB_DOTNET_LOG}'
    bash '${DEVBOOST_ROOT}/modules/dotnet-lsp/install.sh'
  " 2>&1
}

_run_dotnet_lsp_no_fresh() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${_clean_bin}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='fedora'
    export OS_FAMILY='fedora'
    export STUB_DOTNET_LOG='${STUB_DOTNET_LOG}'
    bash '${DEVBOOST_ROOT}/modules/dotnet-lsp/install.sh'
  " 2>&1
}

_run_verify_dotnet_lsp() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/dotnet-lsp/verify.sh'
  " 2>&1
}

# ===========================================================================
# dotnet-sdk
# ===========================================================================

@test "dotnet-sdk: installs the pinned in-distro SDK package via dnf" {
  run _run_dotnet_sdk
  [ "$status" -eq 0 ]
  grep -q 'install -y dotnet-sdk-10.0' "${STUB_DNF_LOG}"
}

@test "dotnet-sdk: idempotent — skips install when a 10.* SDK is already present" {
  export STUB_DOTNET_SDKS="10.0.100 [/usr/lib64/dotnet/sdk]"
  run _run_dotnet_sdk
  [ "$status" -eq 0 ]
  # dnf must NOT have been invoked for the SDK package.
  ! grep -q 'install -y dotnet-sdk-10.0' "${STUB_DNF_LOG}"
}

@test "dotnet-sdk: verify GREEN when a 10.* SDK is listed" {
  export STUB_DOTNET_SDKS="10.0.100 [/usr/lib64/dotnet/sdk]"
  run _run_verify_dotnet_sdk
  [ "$status" -eq 0 ]
}

@test "dotnet-sdk: verify RED when no SDK is listed" {
  export STUB_DOTNET_SDKS=""
  run _run_verify_dotnet_sdk
  [ "$status" -ne 0 ]
}

@test "dotnet-sdk: verify RED when only a non-10 SDK is listed" {
  export STUB_DOTNET_SDKS="9.0.100 [/usr/lib64/dotnet/sdk]"
  run _run_verify_dotnet_sdk
  [ "$status" -ne 0 ]
}

@test "dotnet-sdk: module [install] only targets fedora" {
  run _module_install_cmd dotnet-sdk fedora fedora
  [ "$status" -eq 0 ]
  [[ "$output" == *"modules/dotnet-sdk/install.sh"* ]]
}

@test "dotnet-sdk: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install dotnet-sdk ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# aspire
# ===========================================================================

@test "aspire: installs the Aspire CLI as a global dotnet tool" {
  run _run_aspire
  [ "$status" -eq 0 ]
  grep -q 'tool install -g Aspire.Cli' "${STUB_DOTNET_LOG}"
}

@test "aspire: aspire binary resolves after install" {
  run _run_aspire
  [ "$status" -eq 0 ]
  # The stub's `dotnet tool install` drops `aspire` next to the resolved dotnet (the clean farm).
  [ -x "${_clean_bin}/aspire" ]
}

@test "aspire: idempotent — re-run when aspire present is a no-op skip" {
  _run_aspire >/dev/null
  : > "${STUB_DOTNET_LOG}"
  run _run_aspire
  [ "$status" -eq 0 ]
  # Second run must not re-attempt the tool install (aspire already present).
  ! grep -q 'tool install -g Aspire.Cli' "${STUB_DOTNET_LOG}"
}

@test "aspire: requires dotnet-sdk in module metadata" {
  run cat "${DEVBOOST_ROOT}/modules/aspire/module.toml"
  [[ "$output" == *"dotnet-sdk"* ]]
}

@test "aspire: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install aspire ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# dotnet-lsp
# ===========================================================================

@test "dotnet-lsp: installs csharp-ls and csharpier as global dotnet tools" {
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  grep -q 'tool install -g csharp-ls' "${STUB_DOTNET_LOG}"
  grep -q 'tool install -g csharpier' "${STUB_DOTNET_LOG}"
}

@test "dotnet-lsp: wires lsp.csharp (enabled, absolute dotnet-tool command)" {
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.lsp.csharp.enabled' "${FRESH_CONFIG}")" = "true" ]
  [ "$(jq -r '.lsp.csharp.command' "${FRESH_CONFIG}")" = "${HOME}/.dotnet/tools/csharp-ls" ]
}

@test "dotnet-lsp: seeds base config when absent (preserves base keys)" {
  [ ! -f "${FRESH_CONFIG}" ]
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  [ -f "${FRESH_CONFIG}" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "catppuccin-mocha" ]
  [ "$(jq -r '.editor.format_on_save' "${FRESH_CONFIG}")" = "true" ]
}

@test "dotnet-lsp: jq-merge preserves a pre-existing custom key" {
  mkdir -p "$(dirname "${FRESH_CONFIG}")"
  printf '{ "version":1, "theme":"my-theme", "custom":"keep-me", "lsp":{} }\n' > "${FRESH_CONFIG}"
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  [ "$(jq -r '.custom' "${FRESH_CONFIG}")" = "keep-me" ]
  [ "$(jq -r '.theme' "${FRESH_CONFIG}")" = "my-theme" ]
}

@test "dotnet-lsp: idempotent — re-run leaves config.json unchanged" {
  _run_dotnet_lsp >/dev/null
  local h1; h1="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  local h2; h2="$(jq -S . "${FRESH_CONFIG}" | sha256sum)"
  [ "${h1}" = "${h2}" ]
}

@test "dotnet-lsp: idempotent — re-run skips tool installs when present" {
  _run_dotnet_lsp >/dev/null
  : > "${STUB_DOTNET_LOG}"
  run _run_dotnet_lsp
  [ "$status" -eq 0 ]
  ! grep -q 'tool install -g csharp-ls' "${STUB_DOTNET_LOG}"
  ! grep -q 'tool install -g csharpier' "${STUB_DOTNET_LOG}"
}

@test "dotnet-lsp: fresh missing — module fails NAMING the editor" {
  run _run_dotnet_lsp_no_fresh
  [ "$status" -ne 0 ]
  [[ "$output" == *"fresh"* ]]
  [[ "$output" == *"not installed"* ]]
}

@test "dotnet-lsp: verify GREEN after provisioning" {
  _run_dotnet_lsp >/dev/null
  run _run_verify_dotnet_lsp
  [ "$status" -eq 0 ]
}

@test "dotnet-lsp: verify RED before provisioning (no config)" {
  run _run_verify_dotnet_lsp
  [ "$status" -ne 0 ]
}

@test "dotnet-lsp: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install dotnet-lsp ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# templates/dotnet
# ===========================================================================

@test "templates/dotnet: .fresh/config.json present with csharpier formatter" {
  local cfg="${DEVBOOST_ROOT}/templates/dotnet/.fresh/config.json"
  [ -f "${cfg}" ]
  # Valid JSON.
  jq -e . "${cfg}" >/dev/null
  # The C# formatter is csharpier.
  jq -e '[.. | strings | select(test("csharpier"))] | length > 0' "${cfg}" >/dev/null
}

@test "templates/dotnet: AppHost shows persistent shared infra" {
  local apphost
  apphost="$(ls "${DEVBOOST_ROOT}"/templates/dotnet/AppHost.cs "${DEVBOOST_ROOT}"/templates/dotnet/Program.cs 2>/dev/null | head -n1)"
  [ -n "${apphost}" ]
  grep -q 'WithDataVolume' "${apphost}"
  grep -q 'ContainerLifetime.Persistent' "${apphost}"
}

@test "templates/dotnet: README documents the aspire new / dotnet run flow" {
  local readme="${DEVBOOST_ROOT}/templates/dotnet/README.md"
  [ -f "${readme}" ]
  grep -q 'aspire new' "${readme}"
  grep -q 'dotnet run' "${readme}"
}
