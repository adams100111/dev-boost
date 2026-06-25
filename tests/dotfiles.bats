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
# Helper: run modules/dotfiles/install.sh in a subshell with stub env.
# ---------------------------------------------------------------------------
_run_dotfiles_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_CHEZMOI_LOG='${STUB_CHEZMOI_LOG}'
    export STUB_CHEZMOI_APPLY_FAIL='${STUB_CHEZMOI_APPLY_FAIL:-0}'
    bash '${DEVBOOST_ROOT}/modules/dotfiles/install.sh'
  " 2>&1
}

# Helper: evaluate the dotfiles verify expression in a subshell.
_run_dotfiles_verify() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    [ -f \"\${HOME}/.config/starship.toml\" ] && grep -q 'devboost' \"\${HOME}/.bashrc\"
  " 2>&1
}

# Helper: evaluate the bash-config verify expression (read from module.toml) in a subshell.
# Reads the verify= line, strips the outer TOML quotes, then passes to bash -c via env.
_run_bash_config_verify() {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/bash-config/module.toml" \
          | sed 's/^verify[[:space:]]*=[[:space:]]*"\(.*\)"$/\1/' \
          | sed 's/\\"/"/g')"
  HOME="${HOME}" bash -c "${vcmd}" 2>&1
}

# ===========================================================================
# T013 — chezmoi source tree shape
# ===========================================================================

@test "dotfiles: chezmoi source dot_bashrc exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_bashrc" ]
}

@test "dotfiles: dot_bashrc contains devboost sentinel comment" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains starship init line" {
  grep -q 'starship init bash' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains atuin init line" {
  grep -q 'atuin init bash' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains zoxide init line" {
  grep -q 'zoxide init bash' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains direnv hook line" {
  grep -q 'direnv hook bash' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains fzf key-bindings line" {
  grep -q 'fzf' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: dot_bashrc contains NO secrets or tokens" {
  # Reject patterns: API keys, tokens, passwords embedded in the file.
  ! grep -qiE 'ghp_[A-Za-z0-9]+|password\s*=|secret\s*=|ANTHROPIC_API_KEY\s*=' \
    "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: chezmoi source dot_tmux.conf exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_tmux.conf" ]
}

@test "dotfiles: dot_tmux.conf contains devboost sentinel" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_tmux.conf"
}

@test "dotfiles: chezmoi source dot_config/starship.toml exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/starship.toml" ]
}

@test "dotfiles: dot_config/starship.toml contains devboost sentinel" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_config/starship.toml"
}

@test "dotfiles: chezmoi source dot_config/ghostty/config exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/ghostty/config" ]
}

@test "dotfiles: dot_config/ghostty/config contains devboost sentinel" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_config/ghostty/config"
}

@test "dotfiles: dot_config/ghostty/config contains Ptyxis Mono gotcha note" {
  grep -qi 'ptyxis' "${DEVBOOST_ROOT}/dotfiles/dot_config/ghostty/config"
}

@test "dotfiles: chezmoi source dot_config/atuin/config.toml exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml" ]
}

@test "dotfiles: dot_config/atuin/config.toml contains devboost sentinel" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}

@test "dotfiles: dot_config/atuin/config.toml contains NO secrets or tokens" {
  ! grep -qiE 'key\s*=\s*"[A-Za-z0-9+/]{20,}"' \
    "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}

@test "dotfiles: private_dot_claude skeleton directory exists in repo" {
  [ -d "${DEVBOOST_ROOT}/dotfiles/private_dot_claude" ]
}

# ===========================================================================
# T015 — modules/dotfiles shape
# ===========================================================================

@test "dotfiles: modules/dotfiles/module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/dotfiles/module.toml" ]
}

@test "dotfiles: modules/dotfiles/install.sh exists" {
  [ -f "${DEVBOOST_ROOT}/modules/dotfiles/install.sh" ]
}

@test "dotfiles: module category is shell" {
  grep -q 'category.*=.*"shell"' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: module requires starship" {
  grep -q '"starship"' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: module requires atuin" {
  grep -q '"atuin"' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: module requires zoxide" {
  grep -q '"zoxide"' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: module requires direnv" {
  grep -q '"direnv"' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: install command references install.sh" {
  grep -q 'install.sh' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: verify checks starship.toml present" {
  grep -q 'starship.toml' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml"
}

@test "dotfiles: verify checks devboost sentinel in bashrc" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/dotfiles/module.toml")"
  [[ "${vcmd}" == *"devboost"* ]]
}

# ===========================================================================
# T015 — modules/bash-config shape
# ===========================================================================

@test "bash-config: modules/bash-config/module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/bash-config/module.toml" ]
}

@test "bash-config: module requires dotfiles" {
  grep -q '"dotfiles"' "${DEVBOOST_ROOT}/modules/bash-config/module.toml"
}

@test "bash-config: module category is shell" {
  grep -q 'category.*=.*"shell"' "${DEVBOOST_ROOT}/modules/bash-config/module.toml"
}

# ===========================================================================
# T015 — bash-config verify RED/GREEN
# ===========================================================================

@test "bash-config: verify is RED in pristine scratch HOME (before dotfiles apply)" {
  # No install has run — scratch HOME is empty; verify must fail.
  run _run_bash_config_verify
  [ "$status" -ne 0 ]
}

@test "bash-config: verify is GREEN after dotfiles apply" {
  _run_dotfiles_install >/dev/null 2>&1
  run _run_bash_config_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T014 — chezmoi apply (stubbed) writes managed files
# ===========================================================================

@test "dotfiles: install.sh exits 0 on success" {
  run _run_dotfiles_install
  [ "$status" -eq 0 ]
}

@test "dotfiles: install.sh calls chezmoi apply" {
  run _run_dotfiles_install
  [ "$status" -eq 0 ]
  grep -q "chezmoi apply" "${STUB_CHEZMOI_LOG}"
}

@test "dotfiles: chezmoi apply --source points at DEVBOOST_ROOT/dotfiles tree" {
  _run_dotfiles_install
  # The stub records: chezmoi apply --source <src> --destination <dest>
  local parsed="${STUB_CHEZMOI_LOG}.parsed"
  [ -f "${parsed}" ]
  grep -q "apply --source.*${DEVBOOST_ROOT}/dotfiles" "${parsed}"
}

@test "dotfiles: apply writes ~/.bashrc into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.bashrc" ]
}

@test "dotfiles: apply writes ~/.config/starship.toml into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/starship.toml" ]
}

@test "dotfiles: apply writes ~/.tmux.conf into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.tmux.conf" ]
}

# ===========================================================================
# T014 — re-apply is idempotent: EXACTLY ONE copy of each init line
# ===========================================================================

@test "dotfiles: re-apply — starship init line appears EXACTLY ONCE in ~/.bashrc" {
  # First apply
  _run_dotfiles_install >/dev/null 2>&1
  # Second apply (should be a no-op for the bashrc content)
  _run_dotfiles_install >/dev/null 2>&1
  local count
  count="$(grep -c 'starship init bash' "${HOME}/.bashrc" 2>/dev/null || printf '0')"
  [ "${count}" -eq 1 ]
}

@test "dotfiles: re-apply — atuin init line appears EXACTLY ONCE in ~/.bashrc" {
  _run_dotfiles_install >/dev/null 2>&1
  _run_dotfiles_install >/dev/null 2>&1
  local count
  count="$(grep -c 'atuin init bash' "${HOME}/.bashrc" 2>/dev/null || printf '0')"
  [ "${count}" -eq 1 ]
}

@test "dotfiles: re-apply — zoxide init line appears EXACTLY ONCE in ~/.bashrc" {
  _run_dotfiles_install >/dev/null 2>&1
  _run_dotfiles_install >/dev/null 2>&1
  local count
  count="$(grep -c 'zoxide init bash' "${HOME}/.bashrc" 2>/dev/null || printf '0')"
  [ "${count}" -eq 1 ]
}

@test "dotfiles: re-apply — direnv hook line appears EXACTLY ONCE in ~/.bashrc" {
  _run_dotfiles_install >/dev/null 2>&1
  _run_dotfiles_install >/dev/null 2>&1
  local count
  count="$(grep -c 'direnv hook bash' "${HOME}/.bashrc" 2>/dev/null || printf '0')"
  [ "${count}" -eq 1 ]
}

@test "dotfiles: re-apply — fzf init line appears EXACTLY ONCE in ~/.bashrc" {
  _run_dotfiles_install >/dev/null 2>&1
  _run_dotfiles_install >/dev/null 2>&1
  local count
  count="$(grep -c 'fzf' "${HOME}/.bashrc" 2>/dev/null || printf '0')"
  [ "${count}" -eq 1 ]
}

# ===========================================================================
# T014 — verify green only after apply, red before
# ===========================================================================

@test "dotfiles: verify is RED before apply (starship.toml absent)" {
  # No install yet — scratch HOME has no managed files.
  run _run_dotfiles_verify
  [ "$status" -ne 0 ]
}

@test "dotfiles: verify is GREEN after apply" {
  _run_dotfiles_install >/dev/null 2>&1
  run _run_dotfiles_verify
  [ "$status" -eq 0 ]
}

# ===========================================================================
# T014 — failure path
# ===========================================================================

@test "dotfiles: install.sh exits non-zero when chezmoi apply fails" {
  export STUB_CHEZMOI_APPLY_FAIL=1
  run _run_dotfiles_install
  [ "$status" -ne 0 ]
}

@test "dotfiles: install.sh failure output names the failed operation" {
  export STUB_CHEZMOI_APPLY_FAIL=1
  run _run_dotfiles_install
  [[ "$output" == *"chezmoi"* ]] || [[ "$output" == *"apply"* ]] || [[ "$output" == *"dotfiles"* ]]
}

@test "dotfiles: install.sh never echoes secrets or tokens" {
  run _run_dotfiles_install
  [[ "$output" != *"ghp_"* ]]
  [[ "$output" != *"ANTHROPIC_API_KEY"* ]]
}

# ===========================================================================
# T013 — bat config (Catppuccin Mocha)
# ===========================================================================

@test "dotfiles: chezmoi source dot_config/bat/config exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config" ]
}

@test "dotfiles: bat config has devboost sentinel + style=full" {
  grep -q 'devboost' "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config"
  grep -q -- '--style="full"' "${DEVBOOST_ROOT}/dotfiles/dot_config/bat/config"
}

@test "dotfiles: apply writes ~/.config/bat/config into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/bat/config" ]
}

@test "dotfiles: chezmoi source dot_config/ripgrep/ripgreprc exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc" ]
}

@test "dotfiles: ripgreprc ignores node_modules and lockfiles" {
  grep -q -- '--glob=!node_modules/' "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc"
  grep -qF -- '--glob=!*.lock' "${DEVBOOST_ROOT}/dotfiles/dot_config/ripgrep/ripgreprc"
}

@test "dotfiles: dot_bashrc exports RIPGREP_CONFIG_PATH" {
  grep -q 'export RIPGREP_CONFIG_PATH=' "${DEVBOOST_ROOT}/dotfiles/dot_bashrc"
}

@test "dotfiles: apply writes ~/.config/ripgrep/ripgreprc into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/ripgrep/ripgreprc" ]
}

@test "dotfiles: chezmoi source dot_config/lazygit/config.yml exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml" ]
}

@test "dotfiles: lazygit config wires delta paging + nerdfonts 3" {
  grep -q 'pager: delta' "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml"
  grep -q 'nerdFontsVersion: "3"' "${DEVBOOST_ROOT}/dotfiles/dot_config/lazygit/config.yml"
}

@test "dotfiles: apply writes ~/.config/lazygit/config.yml into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/lazygit/config.yml" ]
}

@test "dotfiles: chezmoi source dot_config/git/config exists in repo" {
  [ -f "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config" ]
}

@test "dotfiles: git config sets delta as pager and NO identity/credentials" {
  grep -q 'pager = delta' "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config"
  # must NOT manage identity/credentials (those belong to the secrets module / ~/.gitconfig)
  ! grep -qiE '^\s*(email|name|helper)\s*=' "${DEVBOOST_ROOT}/dotfiles/dot_config/git/config"
}

@test "dotfiles: apply writes ~/.config/git/config into scratch HOME" {
  _run_dotfiles_install
  [ -f "${HOME}/.config/git/config" ]
}

@test "dotfiles: atuin config enriches up-key (directory) + enter_accept" {
  grep -q 'filter_mode_shell_up_key_binding = "directory"' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
  grep -q 'enter_accept = true' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}

@test "dotfiles: atuin config has a history_filter for secret scrubbing" {
  grep -q 'history_filter' "${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
}

@test "dotfiles: atuin history_filter is TOP-LEVEL (before [settings] header)" {
  # In TOML, keys after a table header belong to that table. history_filter must be
  # a root-table (top-level) array, so it MUST appear before the [settings] line.
  local cfg="${DEVBOOST_ROOT}/dotfiles/dot_config/atuin/config.toml"
  local hf_line settings_line
  hf_line="$(grep -n '^history_filter' "${cfg}" | head -n1 | cut -d: -f1)"
  settings_line="$(grep -n '^\[settings\]' "${cfg}" | head -n1 | cut -d: -f1)"
  [ -n "${hf_line}" ]
  [ -n "${settings_line}" ]
  [ "${hf_line}" -lt "${settings_line}" ]
}
