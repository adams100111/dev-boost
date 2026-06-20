load test_helper

# The full real profiles.toml at repo root is under test here.
# We deliberately set DEVBOOST_PROFILES to the real file, NOT the fixture.
setup() {
  load_lib log.sh
  load_lib toml.sh
  load_lib profile.sh
  export DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml"
}

# Expected base member count (per contracts/profiles.md)
_EXPECTED_BASE_COUNT=21

# Expected base members (must all appear in profile_expand base output)
_EXPECTED_BASE_MEMBERS=(
  secrets ssh-setup rpmfusion dnf-tune fedora-third-party flatpak
  coreutils git curl wget unzip jq htop ripgrep fd fzf tmux
  build-tools mise chezmoi docker
)

# ---------------------------------------------------------------------------
# profile_expand base: membership and count
# ---------------------------------------------------------------------------
@test "profiles.toml: profile_expand base yields exactly ${_EXPECTED_BASE_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand base | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_BASE_COUNT}" ]
}

@test "profiles.toml: profile_expand base contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand base | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_BASE_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

@test "profiles.toml: base profile is defined (profile_names includes base)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"base"* ]]
}

# ---------------------------------------------------------------------------
# T019 — full depsort resolution against real modules/
# ---------------------------------------------------------------------------
@test "devboost list --profile base: resolves without cycle, all 21 modules present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile base
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
  local expected_count=21
  local actual_count
  actual_count="$(printf '%s\n' "$output" | grep -c .)"
  [ "$actual_count" -eq "$expected_count" ]
  # Assert every base member appears in the output
  for module in "${_EXPECTED_BASE_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING from list output: ${module}"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T003 — profile_expand cli: membership and count
# ---------------------------------------------------------------------------
_EXPECTED_CLI_COUNT=18
_EXPECTED_CLI_MEMBERS=(
  eza bat btop zoxide atuin direnv delta lazygit lazydocker
  dust duf sd yq gh tealdeer tpm fastfetch claude-code
)

@test "profiles.toml: profile_expand cli yields exactly ${_EXPECTED_CLI_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand cli | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_CLI_COUNT}" ]
}

@test "profiles.toml: profile_expand cli contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand cli | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_CLI_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T003 — profile_expand shell: membership and count
# ---------------------------------------------------------------------------
_EXPECTED_SHELL_COUNT=5
_EXPECTED_SHELL_MEMBERS=(
  starship bash-config ghostty nerd-fonts dotfiles
)

@test "profiles.toml: profile_expand shell yields exactly ${_EXPECTED_SHELL_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand shell | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_SHELL_COUNT}" ]
}

@test "profiles.toml: profile_expand shell contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand shell | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_SHELL_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T016 — full depsort resolution: cli+shell against real modules/
# ---------------------------------------------------------------------------
_EXPECTED_CLI_SHELL_CLI_MEMBERS=(
  eza bat btop zoxide atuin direnv delta lazygit lazydocker
  dust duf sd yq gh tealdeer tpm fastfetch claude-code
)
_EXPECTED_CLI_SHELL_SHELL_MEMBERS=(
  starship bash-config ghostty nerd-fonts dotfiles
)

@test "devboost list --profile cli,shell: resolves without cycle, exit 0" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile cli,shell
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
}

@test "devboost list --profile cli,shell: all 18 cli module names present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile cli,shell
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_CLI_SHELL_CLI_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING cli module from list output: ${module}"; return 1; }
  done
}

@test "devboost list --profile cli,shell: all 5 shell module names present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile cli,shell
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_CLI_SHELL_SHELL_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING shell module from list output: ${module}"; return 1; }
  done
}

@test "devboost list --profile cli,shell: mise appears before claude-code" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile cli,shell
  [ "$status" -eq 0 ]
  local mise_line claude_line
  mise_line="$(printf '%s\n' "$output" | grep -n '^mise$' | cut -d: -f1)"
  claude_line="$(printf '%s\n' "$output" | grep -n '^claude-code$' | cut -d: -f1)"
  [ -n "$mise_line" ]   || { echo "mise not found in output"; return 1; }
  [ -n "$claude_line" ] || { echo "claude-code not found in output"; return 1; }
  [ "$mise_line" -lt "$claude_line" ] \
    || { echo "mise (line $mise_line) must appear before claude-code (line $claude_line)"; return 1; }
}

@test "devboost list --profile cli,shell: init tools (starship/atuin/zoxide/direnv) before dotfiles before bash-config" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile cli,shell
  [ "$status" -eq 0 ]
  local dotfiles_line bash_config_line starship_line atuin_line zoxide_line direnv_line
  dotfiles_line="$(printf '%s\n' "$output" | grep -n '^dotfiles$'   | cut -d: -f1)"
  bash_config_line="$(printf '%s\n' "$output" | grep -n '^bash-config$' | cut -d: -f1)"
  starship_line="$(printf '%s\n' "$output" | grep -n '^starship$'   | cut -d: -f1)"
  atuin_line="$(printf '%s\n' "$output" | grep -n '^atuin$'      | cut -d: -f1)"
  zoxide_line="$(printf '%s\n' "$output" | grep -n '^zoxide$'     | cut -d: -f1)"
  direnv_line="$(printf '%s\n' "$output" | grep -n '^direnv$'     | cut -d: -f1)"
  # All must be present
  [ -n "$dotfiles_line" ]    || { echo "dotfiles not found";    return 1; }
  [ -n "$bash_config_line" ] || { echo "bash-config not found"; return 1; }
  [ -n "$starship_line" ]    || { echo "starship not found";    return 1; }
  [ -n "$atuin_line" ]       || { echo "atuin not found";       return 1; }
  [ -n "$zoxide_line" ]      || { echo "zoxide not found";      return 1; }
  [ -n "$direnv_line" ]      || { echo "direnv not found";      return 1; }
  # dotfiles before bash-config
  [ "$dotfiles_line" -lt "$bash_config_line" ] \
    || { echo "dotfiles (line $dotfiles_line) must appear before bash-config (line $bash_config_line)"; return 1; }
  # init tools before dotfiles
  [ "$starship_line" -lt "$dotfiles_line" ] \
    || { echo "starship (line $starship_line) must appear before dotfiles (line $dotfiles_line)"; return 1; }
  [ "$atuin_line" -lt "$dotfiles_line" ] \
    || { echo "atuin (line $atuin_line) must appear before dotfiles (line $dotfiles_line)"; return 1; }
  [ "$zoxide_line" -lt "$dotfiles_line" ] \
    || { echo "zoxide (line $zoxide_line) must appear before dotfiles (line $dotfiles_line)"; return 1; }
  [ "$direnv_line" -lt "$dotfiles_line" ] \
    || { echo "direnv (line $direnv_line) must appear before dotfiles (line $dotfiles_line)"; return 1; }
}

# ---------------------------------------------------------------------------
@test "devboost list --profile base: secrets appears before chezmoi and ssh-setup" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile base
  [ "$status" -eq 0 ]
  local secrets_line chezmoi_line ssh_line
  secrets_line="$(printf '%s\n' "$output" | grep -n '^secrets$' | cut -d: -f1)"
  chezmoi_line="$(printf '%s\n' "$output" | grep -n '^chezmoi$' | cut -d: -f1)"
  ssh_line="$(printf '%s\n' "$output" | grep -n '^ssh-setup$' | cut -d: -f1)"
  # secrets must be present
  [ -n "$secrets_line" ] || { echo "secrets not found in output"; return 1; }
  # chezmoi and ssh-setup must come after secrets
  [ "$chezmoi_line" -gt "$secrets_line" ] \
    || { echo "chezmoi (line $chezmoi_line) must come after secrets (line $secrets_line)"; return 1; }
  [ "$ssh_line" -gt "$secrets_line" ] \
    || { echo "ssh-setup (line $ssh_line) must come after secrets (line $secrets_line)"; return 1; }
}
