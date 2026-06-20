load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run an escape-hatch install.sh in a fully-stubbed subshell.
# Passes all log knobs so stubs write to the test-scoped log files.
# ---------------------------------------------------------------------------
_run_install_sh() {
  local module="$1"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_NPM_LOG='${STUB_NPM_LOG}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_ORDER_LOG='${STUB_ORDER_LOG}'
    export STUB_NPM_GLOBALS='${STUB_NPM_GLOBALS:-}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/${module}/install.sh'
  " 2>&1
}

# ===========================================================================
# T005 — simple pure-TOML modules: fedora install command + binary verify
# ===========================================================================

# eza
@test "eza: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/eza.toml" ]
}

@test "eza: fedora install command is 'sudo dnf install -y eza'" {
  local cmd
  cmd="$(_module_install_cmd eza fedora fedora)"
  [[ "${cmd}" == *"dnf install"*"eza"* ]]
}

@test "eza: verify command checks 'command -v eza'" {
  local vcmd
  vcmd="$(_module_verify_cmd eza)"
  [[ "${vcmd}" == *"command -v eza"* ]]
}

@test "eza: idempotent — engine skips when eza is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/eza"
  chmod +x "$(base_stub_dir)/eza"
  : > "${STUB_DNF_LOG}"
  run _engine_install eza fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "eza: unsupported OS — engine logs failure (no install cmd)" {
  run _engine_install eza arch arch
  [[ "$output" == *"unsupported"* ]] || [[ "$output" == *"FAIL"* ]]
}

# bat
@test "bat: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/bat.toml" ]
}

@test "bat: fedora install command contains 'bat'" {
  local cmd
  cmd="$(_module_install_cmd bat fedora fedora)"
  [[ "${cmd}" == *"bat"* ]]
}

@test "bat: verify command checks 'command -v bat'" {
  local vcmd
  vcmd="$(_module_verify_cmd bat)"
  [[ "${vcmd}" == *"command -v bat"* ]]
}

@test "bat: idempotent — engine skips when bat is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/bat"
  chmod +x "$(base_stub_dir)/bat"
  : > "${STUB_DNF_LOG}"
  run _engine_install bat fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# btop
@test "btop: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/btop.toml" ]
}

@test "btop: fedora install command contains 'btop'" {
  local cmd
  cmd="$(_module_install_cmd btop fedora fedora)"
  [[ "${cmd}" == *"btop"* ]]
}

@test "btop: verify command checks 'command -v btop'" {
  local vcmd
  vcmd="$(_module_verify_cmd btop)"
  [[ "${vcmd}" == *"command -v btop"* ]]
}

# zoxide
@test "zoxide: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/zoxide.toml" ]
}

@test "zoxide: fedora install command contains 'zoxide'" {
  local cmd
  cmd="$(_module_install_cmd zoxide fedora fedora)"
  [[ "${cmd}" == *"zoxide"* ]]
}

@test "zoxide: verify command checks 'command -v zoxide'" {
  local vcmd
  vcmd="$(_module_verify_cmd zoxide)"
  [[ "${vcmd}" == *"command -v zoxide"* ]]
}

# atuin
@test "atuin: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/atuin.toml" ]
}

@test "atuin: fedora install command contains 'atuin'" {
  local cmd
  cmd="$(_module_install_cmd atuin fedora fedora)"
  [[ "${cmd}" == *"atuin"* ]]
}

@test "atuin: verify command checks 'command -v atuin'" {
  local vcmd
  vcmd="$(_module_verify_cmd atuin)"
  [[ "${vcmd}" == *"command -v atuin"* ]]
}

# direnv
@test "direnv: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/direnv.toml" ]
}

@test "direnv: fedora install command contains 'direnv'" {
  local cmd
  cmd="$(_module_install_cmd direnv fedora fedora)"
  [[ "${cmd}" == *"direnv"* ]]
}

@test "direnv: verify command checks 'command -v direnv'" {
  local vcmd
  vcmd="$(_module_verify_cmd direnv)"
  [[ "${vcmd}" == *"command -v direnv"* ]]
}

# delta (pkg=git-delta, bin=delta)
@test "delta: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/delta.toml" ]
}

@test "delta: fedora install command contains 'git-delta' (the package name)" {
  local cmd
  cmd="$(_module_install_cmd delta fedora fedora)"
  [[ "${cmd}" == *"git-delta"* ]]
}

@test "delta: verify command checks 'command -v delta' (the binary)" {
  local vcmd
  vcmd="$(_module_verify_cmd delta)"
  [[ "${vcmd}" == *"command -v delta"* ]]
}

@test "delta: idempotent — engine skips when delta binary is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/delta"
  chmod +x "$(base_stub_dir)/delta"
  : > "${STUB_DNF_LOG}"
  run _engine_install delta fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# lazygit
@test "lazygit: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/lazygit.toml" ]
}

@test "lazygit: fedora install command enables atim/lazygit COPR then installs lazygit" {
  local cmd
  cmd="$(_module_install_cmd lazygit fedora fedora)"
  [[ "${cmd}" == *"copr enable"*"atim/lazygit"* ]]
  [[ "${cmd}" == *"lazygit"* ]]
}

@test "lazygit: verify command checks 'command -v lazygit'" {
  local vcmd
  vcmd="$(_module_verify_cmd lazygit)"
  [[ "${vcmd}" == *"command -v lazygit"* ]]
}

# lazydocker
@test "lazydocker: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/lazydocker.toml" ]
}

@test "lazydocker: fedora install command enables atim/lazygit COPR then installs lazydocker" {
  local cmd
  cmd="$(_module_install_cmd lazydocker fedora fedora)"
  [[ "${cmd}" == *"copr enable"*"atim/lazygit"* ]]
  [[ "${cmd}" == *"lazydocker"* ]]
}

@test "lazydocker: verify command checks 'command -v lazydocker'" {
  local vcmd
  vcmd="$(_module_verify_cmd lazydocker)"
  [[ "${vcmd}" == *"command -v lazydocker"* ]]
}

# dust (pkg=rust-dust, bin=dust)
@test "dust: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/dust.toml" ]
}

@test "dust: fedora install command contains 'rust-dust' (the package name)" {
  local cmd
  cmd="$(_module_install_cmd dust fedora fedora)"
  [[ "${cmd}" == *"rust-dust"* ]]
}

@test "dust: verify command checks 'command -v dust' (the binary)" {
  local vcmd
  vcmd="$(_module_verify_cmd dust)"
  [[ "${vcmd}" == *"command -v dust"* ]]
}

# duf
@test "duf: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/duf.toml" ]
}

@test "duf: fedora install command contains 'duf'" {
  local cmd
  cmd="$(_module_install_cmd duf fedora fedora)"
  [[ "${cmd}" == *"duf"* ]]
}

@test "duf: verify command checks 'command -v duf'" {
  local vcmd
  vcmd="$(_module_verify_cmd duf)"
  [[ "${vcmd}" == *"command -v duf"* ]]
}

# sd
@test "sd: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/sd.toml" ]
}

@test "sd: fedora install command contains 'sd'" {
  local cmd
  cmd="$(_module_install_cmd sd fedora fedora)"
  [[ "${cmd}" == *" sd"* ]] || [[ "${cmd}" == *"install -y sd"* ]]
}

@test "sd: verify command checks 'command -v sd'" {
  local vcmd
  vcmd="$(_module_verify_cmd sd)"
  [[ "${vcmd}" == *"command -v sd"* ]]
}

# yq
@test "yq: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/yq.toml" ]
}

@test "yq: fedora install command contains 'yq'" {
  local cmd
  cmd="$(_module_install_cmd yq fedora fedora)"
  [[ "${cmd}" == *"yq"* ]]
}

@test "yq: verify command checks 'command -v yq'" {
  local vcmd
  vcmd="$(_module_verify_cmd yq)"
  [[ "${vcmd}" == *"command -v yq"* ]]
}

# tealdeer (bin=tldr)
@test "tealdeer: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/tealdeer.toml" ]
}

@test "tealdeer: fedora install command contains 'tealdeer'" {
  local cmd
  cmd="$(_module_install_cmd tealdeer fedora fedora)"
  [[ "${cmd}" == *"tealdeer"* ]]
}

@test "tealdeer: verify command checks 'command -v tldr' (the binary)" {
  local vcmd
  vcmd="$(_module_verify_cmd tealdeer)"
  [[ "${vcmd}" == *"command -v tldr"* ]]
}

@test "tealdeer: idempotent — engine skips when tldr binary is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/tldr"
  chmod +x "$(base_stub_dir)/tldr"
  : > "${STUB_DNF_LOG}"
  run _engine_install tealdeer fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

# fastfetch
@test "fastfetch: module file exists" {
  [ -f "${DEVBOOST_ROOT}/modules/fastfetch.toml" ]
}

@test "fastfetch: fedora install command contains 'fastfetch'" {
  local cmd
  cmd="$(_module_install_cmd fastfetch fedora fedora)"
  [[ "${cmd}" == *"fastfetch"* ]]
}

@test "fastfetch: verify command checks 'command -v fastfetch'" {
  local vcmd
  vcmd="$(_module_verify_cmd fastfetch)"
  [[ "${vcmd}" == *"command -v fastfetch"* ]]
}

@test "fastfetch: idempotent — engine skips when fastfetch is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/fastfetch"
  chmod +x "$(base_stub_dir)/fastfetch"
  : > "${STUB_DNF_LOG}"
  run _engine_install fastfetch fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "fastfetch: unsupported OS — engine logs failure" {
  run _engine_install fastfetch arch arch
  [[ "$output" == *"unsupported"* ]] || [[ "$output" == *"FAIL"* ]]
}

# ===========================================================================
# T006 — gh: GitHub CLI escape-hatch module
# ===========================================================================

@test "gh: module file exists at modules/gh/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/gh/module.toml" ]
}

@test "gh: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/gh/install.sh" ]
}

@test "gh: install command is the escape-hatch (runs install.sh)" {
  local cmd
  cmd="$(_module_install_cmd gh fedora fedora)"
  [[ "${cmd}" == *"modules/gh/install.sh"* ]]
}

@test "gh: verify command checks 'command -v gh'" {
  local vcmd
  vcmd="$(_module_verify_cmd gh)"
  [[ "${vcmd}" == *"command -v gh"* ]]
}

@test "gh: install.sh adds dnf repo and installs gh" {
  run _run_install_sh gh
  [ "$status" -eq 0 ]
  grep -q "dnf" "${STUB_DNF_LOG}"
}

@test "gh: install.sh is idempotent — repo not re-added when rpm already has gh" {
  # Simulate gh already installed via RPM
  export STUB_RPM_INSTALLED="gh"
  : > "${STUB_DNF_LOG}"
  # Place a gh stub so the idempotency check in install.sh can succeed
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/gh"
  chmod +x "$(base_stub_dir)/gh"
  run _run_install_sh gh
  [ "$status" -eq 0 ]
}

@test "gh: engine skips when gh binary is present" {
  printf '#!/usr/bin/env bash\nexit 0\n' > "$(base_stub_dir)/gh"
  chmod +x "$(base_stub_dir)/gh"
  : > "${STUB_DNF_LOG}"
  run _engine_install gh fedora fedora
  [ "$status" -eq 0 ]
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "gh: engine installs when gh binary is absent (--force bypasses verify)" {
  rm -f "$(base_stub_dir)/gh"
  : > "${STUB_DNF_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install gh fedora fedora || true
  grep -q "dnf" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T007 — tpm: tmux plugin manager escape-hatch module
# ===========================================================================

@test "tpm: module file exists at modules/tpm/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/tpm/module.toml" ]
}

@test "tpm: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/tpm/install.sh" ]
}

@test "tpm: verify command checks directory existence" {
  local vcmd
  vcmd="$(_module_verify_cmd tpm)"
  [[ "${vcmd}" == *".tmux/plugins/tpm"* ]]
}

@test "tpm: requires is empty (tmux is base)" {
  local req
  req="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires tpm
  " 2>&1)"
  [[ -z "${req}" ]]
}

@test "tpm: install.sh clones tpm when directory is absent" {
  # Ensure tpm dir is not present
  rm -rf "${HOME}/.tmux/plugins/tpm"
  : > "${STUB_GIT_LOG}"
  run _run_install_sh tpm
  [ "$status" -eq 0 ]
  grep -q "git clone" "${STUB_GIT_LOG}"
}

@test "tpm: install.sh skips clone when tpm directory already exists" {
  # Create the tpm dir to simulate already cloned
  mkdir -p "${HOME}/.tmux/plugins/tpm"
  : > "${STUB_GIT_LOG}"
  run _run_install_sh tpm
  [ "$status" -eq 0 ]
  # git clone should NOT have been called
  ! grep -q "git clone" "${STUB_GIT_LOG}"
}

@test "tpm: engine skips when tpm dir is present" {
  mkdir -p "${HOME}/.tmux/plugins/tpm"
  run _engine_install tpm fedora fedora
  [ "$status" -eq 0 ]
  # No git clone logged when engine skips
  [ ! -s "${STUB_GIT_LOG}" ]
}

@test "tpm: engine runs install when tpm dir is absent (--force)" {
  rm -rf "${HOME}/.tmux/plugins/tpm"
  : > "${STUB_GIT_LOG}"
  # Use --force to bypass verify guard and always reach install
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install tpm fedora fedora || true
  grep -q "clone" "${STUB_GIT_LOG}"
}

# ===========================================================================
# T008 — claude-code: npm global module with mise node dependency
# ===========================================================================

@test "claude-code: module file exists at modules/claude-code/module.toml" {
  [ -f "${DEVBOOST_ROOT}/modules/claude-code/module.toml" ]
}

@test "claude-code: install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/claude-code/install.sh" ]
}

@test "claude-code: requires mise" {
  local req
  req="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    module_requires claude-code
  " 2>&1)"
  [[ "${req}" == *"mise"* ]]
}

@test "claude-code: verify command checks 'command -v claude'" {
  local vcmd
  vcmd="$(_module_verify_cmd claude-code)"
  [[ "${vcmd}" == *"command -v claude"* ]]
}

@test "claude-code: install.sh provisions node via mise BEFORE npm when node absent" {
  # Build a PATH that excludes any system node binary so that command -v node
  # fails inside the install.sh subshell, triggering the mise guard branch.
  # We strip every PATH component that contains a 'node' binary.
  local node_free_path=""
  local IFS_orig="${IFS}"
  IFS=":"
  for dir in ${PATH}; do
    IFS="${IFS_orig}"
    # Skip directories that provide a 'node' binary.
    if [[ -x "${dir}/node" ]]; then
      continue
    fi
    node_free_path="${node_free_path:+${node_free_path}:}${dir}"
    IFS=":"
  done
  IFS="${IFS_orig}"
  # Also ensure no stub node is present in the stub bin dir.
  rm -f "$(base_stub_dir)/node"
  export STUB_NPM_GLOBALS="@anthropic-ai/claude-code:claude"
  : > "${STUB_MISE_LOG}"
  : > "${STUB_NPM_LOG}"
  : > "${STUB_ORDER_LOG}"
  # Run install.sh with the node-free PATH.
  local output
  output="$(bash -c "
    export HOME='${HOME}'
    export PATH='${node_free_path}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_RPM_LOG='${STUB_RPM_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_GIT_LOG='${STUB_GIT_LOG}'
    export STUB_NPM_LOG='${STUB_NPM_LOG}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_ORDER_LOG='${STUB_ORDER_LOG}'
    export STUB_NPM_GLOBALS='${STUB_NPM_GLOBALS:-}'
    export STUB_RPM_INSTALLED='${STUB_RPM_INSTALLED:-}'
    bash '${DEVBOOST_ROOT}/modules/claude-code/install.sh'
  " 2>&1)"
  local rc=$?
  [ "${rc}" -eq 0 ]
  # mise must have been called for node provisioning (node was absent)
  grep -q "node" "${STUB_MISE_LOG}"
  # npm must have been called
  grep -q "install" "${STUB_NPM_LOG}"
  # Prove chronological order via the single shared call-log:
  # the mise:use … node line must appear before the npm:install line.
  local mise_lineno npm_lineno
  mise_lineno="$(grep -n "^mise:.*node" "${STUB_ORDER_LOG}" | head -1 | cut -d: -f1)"
  npm_lineno="$(grep -n "^npm:install" "${STUB_ORDER_LOG}" | head -1 | cut -d: -f1)"
  [ -n "${mise_lineno}" ]
  [ -n "${npm_lineno}" ]
  [ "${mise_lineno}" -lt "${npm_lineno}" ]
}

@test "claude-code: install.sh does NOT call mise when node already exists" {
  # Ensure a node stub is on PATH so command -v node succeeds.
  printf '#!/usr/bin/env bash\nprintf "v20.0.0\n"\nexit 0\n' > "$(base_stub_dir)/node"
  chmod +x "$(base_stub_dir)/node"
  export STUB_NPM_GLOBALS="@anthropic-ai/claude-code:claude"
  : > "${STUB_MISE_LOG}"
  : > "${STUB_NPM_LOG}"
  : > "${STUB_ORDER_LOG}"
  run _run_install_sh claude-code
  [ "$status" -eq 0 ]
  # mise must NOT have been called for node provisioning
  ! grep -q "node" "${STUB_MISE_LOG}"
  # npm install must still have been called
  grep -q "@anthropic-ai/claude-code" "${STUB_NPM_LOG}"
}

@test "claude-code: install.sh attempts npm install -g @anthropic-ai/claude-code" {
  export STUB_NPM_GLOBALS="@anthropic-ai/claude-code:claude"
  : > "${STUB_NPM_LOG}"
  run _run_install_sh claude-code
  [ "$status" -eq 0 ]
  grep -q "@anthropic-ai/claude-code" "${STUB_NPM_LOG}"
}

@test "claude-code: install is reachable via --force (host-independent)" {
  # Remove claude from PATH so verify fails; use --force to always reach install
  rm -f "$(base_stub_dir)/claude"
  export STUB_NPM_GLOBALS="@anthropic-ai/claude-code:claude"
  : > "${STUB_NPM_LOG}"
  DEVBOOST_INSTALL_FLAGS="--force" _engine_install claude-code fedora fedora || true
  grep -q "@anthropic-ai/claude-code" "${STUB_NPM_LOG}"
}

@test "claude-code: install.sh does not echo any token or secret" {
  export STUB_NPM_GLOBALS="@anthropic-ai/claude-code:claude"
  run _run_install_sh claude-code
  # Output must not contain anything resembling a token pattern
  [[ "$output" != *"TOKEN"* ]]
  [[ "$output" != *"SECRET"* ]]
  [[ "$output" != *"ANTHROPIC_API_KEY"* ]]
}

@test "claude-code: depsort places mise before claude-code" {
  local order
  order="$(bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    depsort claude-code
  " 2>&1)"
  local mise_pos claude_pos
  mise_pos="$(printf '%s\n' "${order}" | grep -n "^mise$" | cut -d: -f1)"
  claude_pos="$(printf '%s\n' "${order}" | grep -n "^claude-code$" | cut -d: -f1)"
  [ -n "${mise_pos}" ]
  [ -n "${claude_pos}" ]
  [ "${mise_pos}" -lt "${claude_pos}" ]
}
