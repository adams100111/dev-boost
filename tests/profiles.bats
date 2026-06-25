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
_EXPECTED_BASE_COUNT=22

# Expected base members (must all appear in profile_expand base output)
_EXPECTED_BASE_MEMBERS=(
  secrets ssh-setup rpmfusion dnf-tune fedora-third-party flatpak
  coreutils git curl wget unzip jq htop ripgrep fd fzf tmux
  build-tools mise chezmoi chezmoi-repo docker
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
@test "devboost list --profile base: resolves without cycle, all 22 modules present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile base
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
  local expected_count=22
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
@test "devboost list --profile base: secrets appears before ssh-setup and chezmoi-repo" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile base
  [ "$status" -eq 0 ]
  local secrets_line ssh_line chezmoi_repo_line chezmoi_line
  secrets_line="$(printf '%s\n' "$output" | grep -n '^secrets$'      | cut -d: -f1)"
  ssh_line="$(printf '%s\n'     "$output" | grep -n '^ssh-setup$'    | cut -d: -f1)"
  chezmoi_repo_line="$(printf '%s\n' "$output" | grep -n '^chezmoi-repo$' | cut -d: -f1)"
  chezmoi_line="$(printf '%s\n' "$output" | grep -n '^chezmoi$'      | cut -d: -f1)"
  # All must be present
  [ -n "$secrets_line" ]      || { echo "secrets not found in output";      return 1; }
  [ -n "$ssh_line" ]          || { echo "ssh-setup not found in output";    return 1; }
  [ -n "$chezmoi_repo_line" ] || { echo "chezmoi-repo not found in output"; return 1; }
  [ -n "$chezmoi_line" ]      || { echo "chezmoi not found in output";      return 1; }
  # ssh-setup requires secrets, so secrets must precede ssh-setup
  [ "$ssh_line" -gt "$secrets_line" ] \
    || { echo "ssh-setup (line $ssh_line) must come after secrets (line $secrets_line)"; return 1; }
  # chezmoi-repo requires both chezmoi and secrets, so both must precede it
  [ "$chezmoi_line" -lt "$chezmoi_repo_line" ] \
    || { echo "chezmoi (line $chezmoi_line) must come before chezmoi-repo (line $chezmoi_repo_line)"; return 1; }
  [ "$secrets_line" -lt "$chezmoi_repo_line" ] \
    || { echo "secrets (line $secrets_line) must come before chezmoi-repo (line $chezmoi_repo_line)"; return 1; }
}

# ---------------------------------------------------------------------------
# T005 — profile_expand gnome / gnome-aesthetics / gnome-theme (TOML-only)
# ---------------------------------------------------------------------------

_EXPECTED_GNOME_COUNT=3
_EXPECTED_GNOME_MEMBERS=(
  gnome-settings gnome-extensions gnome-manager-apps
)

@test "profiles.toml: gnome profile is defined (profile_names includes gnome)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"gnome"* ]]
}

@test "profiles.toml: profile_expand gnome yields exactly ${_EXPECTED_GNOME_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_GNOME_COUNT}" ]
}

@test "profiles.toml: profile_expand gnome contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_GNOME_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

@test "profiles.toml: gnome-aesthetics profile is defined (profile_names includes gnome-aesthetics)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"gnome-aesthetics"* ]]
}

@test "profiles.toml: profile_expand gnome-aesthetics yields exactly 1 module" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome-aesthetics | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "profiles.toml: profile_expand gnome-aesthetics contains module gnome-aesthetics-bundle" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome-aesthetics | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"gnome-aesthetics-bundle"* ]]
}

@test "profiles.toml: gnome-theme profile is defined (profile_names includes gnome-theme)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"gnome-theme"* ]]
}

@test "profiles.toml: profile_expand gnome-theme yields exactly 1 module" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome-theme | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "profiles.toml: profile_expand gnome-theme contains module gnome-theme-bundle" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand gnome-theme | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"gnome-theme-bundle"* ]]
}

# ---------------------------------------------------------------------------
# T014 — full depsort resolution: gnome + opt-in bundles against real modules/
# ---------------------------------------------------------------------------

@test "devboost list --profile gnome: resolves without cycle, exit 0, all 3 modules present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile gnome
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
  local actual_count
  actual_count="$(printf '%s\n' "$output" | grep -c .)"
  [ "$actual_count" -eq 3 ]
  for module in gnome-settings gnome-extensions gnome-manager-apps; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING from list output: ${module}"; return 1; }
  done
}

@test "devboost list --profile gnome: gnome-settings ordered before gnome-extensions" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile gnome
  [ "$status" -eq 0 ]
  local settings_line extensions_line
  settings_line="$(printf '%s\n' "$output" | grep -n '^gnome-settings$'   | cut -d: -f1)"
  extensions_line="$(printf '%s\n' "$output" | grep -n '^gnome-extensions$' | cut -d: -f1)"
  [ -n "$settings_line" ]   || { echo "gnome-settings not found in output";   return 1; }
  [ -n "$extensions_line" ] || { echo "gnome-extensions not found in output"; return 1; }
  [ "$settings_line" -lt "$extensions_line" ] \
    || { echo "gnome-settings (line $settings_line) must appear before gnome-extensions (line $extensions_line)"; return 1; }
}

@test "devboost list --profile gnome: gnome-settings ordered before gnome-manager-apps" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile gnome
  [ "$status" -eq 0 ]
  local settings_line manager_line
  settings_line="$(printf '%s\n' "$output" | grep -n '^gnome-settings$'     | cut -d: -f1)"
  manager_line="$(printf '%s\n' "$output" | grep -n '^gnome-manager-apps$' | cut -d: -f1)"
  [ -n "$settings_line" ] || { echo "gnome-settings not found in output";    return 1; }
  [ -n "$manager_line" ]  || { echo "gnome-manager-apps not found in output"; return 1; }
  [ "$settings_line" -lt "$manager_line" ] \
    || { echo "gnome-settings (line $settings_line) must appear before gnome-manager-apps (line $manager_line)"; return 1; }
}

@test "devboost list --profile gnome-aesthetics: resolves to gnome-aesthetics-bundle (non-empty, no cycle)" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile gnome-aesthetics
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
  [[ "$output" == *"gnome-aesthetics-bundle"* ]] \
    || { echo "gnome-aesthetics-bundle not found in list output"; return 1; }
  local actual_count
  actual_count="$(printf '%s\n' "$output" | grep -c .)"
  [ "$actual_count" -gt 0 ]
}

@test "devboost list --profile gnome-theme: resolves to gnome-theme-bundle (non-empty, no cycle)" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile gnome-theme
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
  [[ "$output" == *"gnome-theme-bundle"* ]] \
    || { echo "gnome-theme-bundle not found in list output"; return 1; }
  local actual_count
  actual_count="$(printf '%s\n' "$output" | grep -c .)"
  [ "$actual_count" -gt 0 ]
}

# ---------------------------------------------------------------------------
# T003 — profile_expand multimedia (TOML-only membership + count)
# Full depsort test deferred to T010 (polish).
# ---------------------------------------------------------------------------

_EXPECTED_MULTIMEDIA_COUNT=4
_EXPECTED_MULTIMEDIA_MEMBERS=(
  ffmpeg-full codecs va-hwaccel openh264
)

@test "profiles.toml: multimedia profile is defined (profile_names includes multimedia)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"multimedia"* ]]
}

@test "profiles.toml: profile_expand multimedia yields exactly ${_EXPECTED_MULTIMEDIA_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand multimedia | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_MULTIMEDIA_COUNT}" ]
}

@test "profiles.toml: profile_expand multimedia contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand multimedia | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_MULTIMEDIA_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T010 — full depsort resolution: multimedia against real modules/
# ---------------------------------------------------------------------------

@test "devboost list --profile multimedia: resolves without cycle, exit 0" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
}

@test "devboost list --profile multimedia: all 4 multimedia modules present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  for module in ffmpeg-full codecs va-hwaccel openh264; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING from list output: ${module}"; return 1; }
  done
}

@test "devboost list --profile multimedia: transitive rpmfusion present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  [[ "$output" == *"rpmfusion"* ]] \
    || { echo "transitive rpmfusion missing from list output"; return 1; }
}

@test "devboost list --profile multimedia: rpmfusion ordered before ffmpeg-full" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  local rpmfusion_line ffmpeg_line
  rpmfusion_line="$(printf '%s\n' "$output" | grep -n '^rpmfusion$'  | cut -d: -f1)"
  ffmpeg_line="$(printf '%s\n'    "$output" | grep -n '^ffmpeg-full$' | cut -d: -f1)"
  [ -n "$rpmfusion_line" ] || { echo "rpmfusion not found in output";  return 1; }
  [ -n "$ffmpeg_line" ]    || { echo "ffmpeg-full not found in output"; return 1; }
  [ "$rpmfusion_line" -lt "$ffmpeg_line" ] \
    || { echo "rpmfusion (line $rpmfusion_line) must appear before ffmpeg-full (line $ffmpeg_line)"; return 1; }
}

@test "devboost list --profile multimedia: rpmfusion ordered before codecs" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  local rpmfusion_line codecs_line
  rpmfusion_line="$(printf '%s\n' "$output" | grep -n '^rpmfusion$' | cut -d: -f1)"
  codecs_line="$(printf '%s\n'    "$output" | grep -n '^codecs$'    | cut -d: -f1)"
  [ -n "$rpmfusion_line" ] || { echo "rpmfusion not found in output"; return 1; }
  [ -n "$codecs_line" ]    || { echo "codecs not found in output";    return 1; }
  [ "$rpmfusion_line" -lt "$codecs_line" ] \
    || { echo "rpmfusion (line $rpmfusion_line) must appear before codecs (line $codecs_line)"; return 1; }
}

@test "devboost list --profile multimedia: rpmfusion ordered before va-hwaccel" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile multimedia
  [ "$status" -eq 0 ]
  local rpmfusion_line vahwaccel_line
  rpmfusion_line="$(printf '%s\n' "$output" | grep -n '^rpmfusion$'  | cut -d: -f1)"
  vahwaccel_line="$(printf '%s\n' "$output" | grep -n '^va-hwaccel$' | cut -d: -f1)"
  [ -n "$rpmfusion_line" ]  || { echo "rpmfusion not found in output";  return 1; }
  [ -n "$vahwaccel_line" ]  || { echo "va-hwaccel not found in output"; return 1; }
  [ "$rpmfusion_line" -lt "$vahwaccel_line" ] \
    || { echo "rpmfusion (line $rpmfusion_line) must appear before va-hwaccel (line $vahwaccel_line)"; return 1; }
}

# ---------------------------------------------------------------------------
# T003 — profile_expand editors (TOML-only membership + count)
# Full depsort test deferred to T011 (polish).
# ---------------------------------------------------------------------------

_EXPECTED_EDITORS_COUNT=3
_EXPECTED_EDITORS_MEMBERS=(
  vscode fresh fresh-lsp
)

@test "profiles.toml: editors profile is defined (profile_names includes editors)" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"editors"* ]]
}

@test "profiles.toml: profile_expand editors yields exactly ${_EXPECTED_EDITORS_COUNT} modules" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand editors | wc -l | tr -d " "
  '
  [ "$status" -eq 0 ]
  [ "$output" -eq "${_EXPECTED_EDITORS_COUNT}" ]
}

@test "profiles.toml: profile_expand editors contains all required members" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand editors | sort | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for module in "${_EXPECTED_EDITORS_MEMBERS[@]}"; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING module: ${module}"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T011 — full depsort resolution: editors against real modules/
# ---------------------------------------------------------------------------

@test "devboost list --profile editors: resolves without cycle, exit 0" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile editors
  [ "$status" -eq 0 ]
  [[ "$output" != *"cycle"* ]]
}

@test "devboost list --profile editors: all 3 editors modules present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile editors
  [ "$status" -eq 0 ]
  for module in vscode fresh fresh-lsp; do
    [[ "$output" == *"${module}"* ]] \
      || { echo "MISSING from list output: ${module}"; return 1; }
  done
}

@test "devboost list --profile editors: transitive mise present" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile editors
  [ "$status" -eq 0 ]
  [[ "$output" == *"mise"* ]] \
    || { echo "transitive mise missing from list output"; return 1; }
}

@test "devboost list --profile editors: mise ordered before fresh-lsp" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile editors
  [ "$status" -eq 0 ]
  local mise_line lsp_line
  mise_line="$(printf '%s\n' "$output" | grep -n '^mise$'      | cut -d: -f1)"
  lsp_line="$(printf '%s\n'  "$output" | grep -n '^fresh-lsp$' | cut -d: -f1)"
  [ -n "$mise_line" ] || { echo "mise not found in output";      return 1; }
  [ -n "$lsp_line" ]  || { echo "fresh-lsp not found in output"; return 1; }
  [ "$mise_line" -lt "$lsp_line" ] \
    || { echo "mise (line $mise_line) must appear before fresh-lsp (line $lsp_line)"; return 1; }
}

@test "devboost list --profile editors: fresh ordered before fresh-lsp" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile editors
  [ "$status" -eq 0 ]
  local fresh_line lsp_line
  fresh_line="$(printf '%s\n' "$output" | grep -n '^fresh$'     | cut -d: -f1)"
  lsp_line="$(printf '%s\n'   "$output" | grep -n '^fresh-lsp$' | cut -d: -f1)"
  [ -n "$fresh_line" ] || { echo "fresh not found in output";     return 1; }
  [ -n "$lsp_line" ]   || { echo "fresh-lsp not found in output"; return 1; }
  [ "$fresh_line" -lt "$lsp_line" ] \
    || { echo "fresh (line $fresh_line) must appear before fresh-lsp (line $lsp_line)"; return 1; }
}

# ---------------------------------------------------------------------------
# T004 — dev-stacks: 7 stack profiles membership + count (TOML-only).
# Full depsort tests are T026 (polish).
# ---------------------------------------------------------------------------

@test "profiles.toml: all 7 dev-stack profiles are defined" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  for p in python web laravel dotnet data devops react-native; do
    [[ "$output" == *"$p"* ]] || { echo "MISSING profile: $p"; return 1; }
  done
}

_expand_stack() {
  bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand "'"$1"'" | sort | tr "\n" " "
  '
}

@test "profiles.toml: python = uv + python-lsp" {
  run _expand_stack python
  [ "$status" -eq 0 ]; [[ "$output" == *"uv"* && "$output" == *"python-lsp"* ]]
}
@test "profiles.toml: web = web-runtimes + web-lsp" {
  run _expand_stack web
  [ "$status" -eq 0 ]; [[ "$output" == *"web-runtimes"* && "$output" == *"web-lsp"* ]]
}
@test "profiles.toml: laravel = ddev + laravel-lsp" {
  run _expand_stack laravel
  [ "$status" -eq 0 ]; [[ "$output" == *"ddev"* && "$output" == *"laravel-lsp"* ]]
}
@test "profiles.toml: dotnet = dotnet-sdk + aspire + dotnet-lsp" {
  run _expand_stack dotnet
  [ "$status" -eq 0 ]; [[ "$output" == *"dotnet-sdk"* && "$output" == *"aspire"* && "$output" == *"dotnet-lsp"* ]]
}
@test "profiles.toml: data = data-services" {
  run _expand_stack data
  [ "$status" -eq 0 ]; [[ "$output" == *"data-services"* ]]
}
@test "profiles.toml: devops = devops-tools + devops-lsp" {
  run _expand_stack devops
  [ "$status" -eq 0 ]; [[ "$output" == *"devops-tools"* && "$output" == *"devops-lsp"* ]]
}
@test "profiles.toml: react-native = web-runtimes + android-sdk + expo" {
  run _expand_stack react-native
  [ "$status" -eq 0 ]; [[ "$output" == *"web-runtimes"* && "$output" == *"android-sdk"* && "$output" == *"expo"* ]]
}

# ===========================================================================
# T026 — full depsort resolution: 7 dev-stacks against real modules/
# `devboost list --profile <stack>` resolves without cycle (exit 0), surfaces
# every expanded member + transitive deps, and orders each `*-lsp` (and other
# dependents) AFTER its toolchain and after mise/fresh. react-native pulls in
# the web-runtimes module (shared with the web stack).
# ===========================================================================

# Print the resolved module list for a stack profile (one module per line).
_list_profile() {
  env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
      DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
      "${DEVBOOST_ROOT}/bin/devboost" list --profile "$1"
}

# Assert module $2 appears strictly before module $3 in list output $1.
_assert_order() {
  local out="$1" before="$2" after="$3" bl al
  bl="$(printf '%s\n' "$out" | grep -n "^${before}\$" | cut -d: -f1)"
  al="$(printf '%s\n' "$out" | grep -n "^${after}\$"  | cut -d: -f1)"
  [ -n "$bl" ] || { echo "missing ${before} in output"; return 1; }
  [ -n "$al" ] || { echo "missing ${after} in output";  return 1; }
  [ "$bl" -lt "$al" ] || { echo "${before} (line $bl) must precede ${after} (line $al)"; return 1; }
}

# --- python ---------------------------------------------------------------
@test "devboost list --profile python: resolves, members + transitive present" {
  run _list_profile python
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in uv python-lsp mise fresh; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile python: uv/mise/fresh ordered before python-lsp" {
  run _list_profile python
  [ "$status" -eq 0 ]
  _assert_order "$output" uv python-lsp
  _assert_order "$output" mise python-lsp
  _assert_order "$output" fresh python-lsp
}

# --- web -------------------------------------------------------------------
@test "devboost list --profile web: resolves, members + transitive present" {
  run _list_profile web
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in web-runtimes web-lsp mise fresh; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile web: web-runtimes/mise/fresh ordered before web-lsp" {
  run _list_profile web
  [ "$status" -eq 0 ]
  _assert_order "$output" web-runtimes web-lsp
  _assert_order "$output" mise web-lsp
  _assert_order "$output" fresh web-lsp
}

# --- laravel ---------------------------------------------------------------
@test "devboost list --profile laravel: resolves, members + transitive present" {
  run _list_profile laravel
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in ddev laravel-lsp docker mise fresh; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile laravel: ddev/mise/fresh ordered before laravel-lsp" {
  run _list_profile laravel
  [ "$status" -eq 0 ]
  _assert_order "$output" ddev laravel-lsp
  _assert_order "$output" mise laravel-lsp
  _assert_order "$output" fresh laravel-lsp
}

# --- dotnet ----------------------------------------------------------------
@test "devboost list --profile dotnet: resolves, members + transitive present" {
  run _list_profile dotnet
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in dotnet-sdk aspire dotnet-lsp fresh; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile dotnet: dotnet-sdk before aspire and dotnet-lsp; fresh before dotnet-lsp" {
  run _list_profile dotnet
  [ "$status" -eq 0 ]
  _assert_order "$output" dotnet-sdk aspire
  _assert_order "$output" dotnet-sdk dotnet-lsp
  _assert_order "$output" fresh dotnet-lsp
}

# --- data ------------------------------------------------------------------
@test "devboost list --profile data: resolves, data-services + docker present" {
  run _list_profile data
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in data-services docker; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile data: docker ordered before data-services" {
  run _list_profile data
  [ "$status" -eq 0 ]
  _assert_order "$output" docker data-services
}

# --- devops ----------------------------------------------------------------
@test "devboost list --profile devops: resolves, members + transitive present" {
  run _list_profile devops
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in devops-tools devops-lsp mise fresh; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile devops: devops-tools/mise/fresh ordered before devops-lsp" {
  run _list_profile devops
  [ "$status" -eq 0 ]
  _assert_order "$output" devops-tools devops-lsp
  _assert_order "$output" mise devops-lsp
  _assert_order "$output" fresh devops-lsp
}

# --- react-native ----------------------------------------------------------
@test "devboost list --profile react-native: resolves, includes web-runtimes + android-sdk + expo" {
  run _list_profile react-native
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in web-runtimes android-sdk expo mise; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile react-native: web-runtimes ordered before expo; mise before android-sdk" {
  run _list_profile react-native
  [ "$status" -eq 0 ]
  _assert_order "$output" web-runtimes expo
  _assert_order "$output" mise android-sdk
}

# ---------------------------------------------------------------------------
# T005 — apps-and-obsidian: profile membership (TOML-only). Depsort = T019.
# ---------------------------------------------------------------------------
@test "profiles.toml: apps profile is defined with 7 members" {
  run _expand_stack apps
  [ "$status" -eq 0 ]
  for m in obsidian bruno bitwarden flameshot localsend vlc obsidian-sync; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING from apps: $m"; return 1; }
  done
}

# ---------------------------------------------------------------------------
# T019 — apps-and-obsidian: full depsort resolution against real modules/.
# obsidian-sync after obsidian + secrets + ssh-setup; flatpak before each app.
# ---------------------------------------------------------------------------
@test "devboost list --profile apps: resolves, members + transitive present" {
  run _list_profile apps
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in obsidian bruno bitwarden flameshot localsend vlc obsidian-sync flatpak secrets ssh-setup; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "devboost list --profile apps: flatpak before apps; obsidian-sync after obsidian/secrets/ssh-setup" {
  run _list_profile apps
  [ "$status" -eq 0 ]
  _assert_order "$output" flatpak obsidian
  _assert_order "$output" obsidian obsidian-sync
  _assert_order "$output" secrets obsidian-sync
  _assert_order "$output" ssh-setup obsidian-sync
}

# ---------------------------------------------------------------------------
# Spec 9 — dev-hygiene profile membership (TOML-only). Depsort = Polish.
# ---------------------------------------------------------------------------
@test "profiles.toml: dev-hygiene profile = aspire-gc" {
  run _expand_stack dev-hygiene
  [ "$status" -eq 0 ]; [[ "$output" == *"aspire-gc"* ]]
}

@test "devboost list --profile dev-hygiene: resolves, docker before aspire-gc" {
  run _list_profile dev-hygiene
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in aspire-gc docker; do [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }; done
  _assert_order "$output" docker aspire-gc
}

# ---------------------------------------------------------------------------
# Spec 10 — system / hardware-nvidia / optional-editors membership (TOML-only).
# ---------------------------------------------------------------------------
@test "profiles.toml: system profile has snapshot+maintenance+earlyoom+gpu-detect" {
  run _expand_stack system
  [ "$status" -eq 0 ]
  for m in snapper grub-btrfs earlyoom dnf-automatic-security gpu-detect; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "profiles.toml: hardware-nvidia chain members present" {
  run _expand_stack hardware-nvidia
  [ "$status" -eq 0 ]
  for m in nvidia-akmod secureboot-mok nvidia-resign-service nvidia-container-toolkit; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
}
@test "profiles.toml: optional-editors = neovim + jetbrains-toolbox" {
  run _expand_stack optional-editors
  [ "$status" -eq 0 ]; [[ "$output" == *"neovim"* && "$output" == *"jetbrains-toolbox"* ]]
}

# ---------------------------------------------------------------------------
# Spec 10 — full depsort resolution: system / hardware-nvidia / optional-editors.
# ---------------------------------------------------------------------------
@test "devboost list --profile system: resolves, members + transitive rpmfusion present" {
  run _list_profile system
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in snapper snapper-dnf-hook grub-btrfs earlyoom gpu-detect rpmfusion; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
  _assert_order "$output" snapper snapper-dnf-hook
  _assert_order "$output" snapper grub-btrfs
}
@test "devboost list --profile hardware-nvidia: rpmfusion→nvidia-akmod→dependents" {
  run _list_profile hardware-nvidia
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  for m in nvidia-akmod cuda libva-nvidia-driver secureboot-mok nvidia-resign-service nvidia-container-toolkit rpmfusion; do
    [[ "$output" == *"$m"* ]] || { echo "MISSING $m"; return 1; }
  done
  _assert_order "$output" rpmfusion nvidia-akmod
  _assert_order "$output" nvidia-akmod secureboot-mok
  _assert_order "$output" nvidia-akmod nvidia-resign-service
}
@test "devboost list --profile optional-editors: resolves neovim + jetbrains-toolbox" {
  run _list_profile optional-editors
  [ "$status" -eq 0 ]; [[ "$output" != *"cycle"* ]]
  [[ "$output" == *"neovim"* && "$output" == *"jetbrains-toolbox"* ]]
}

@test "profiles.toml: security-cli = pass + pass-store (opt-in, not full)" {
  run _expand_stack security-cli
  [ "$status" -eq 0 ]; [[ "$output" == *"pass"* && "$output" == *"pass-store"* ]]
}

# ---------------------------------------------------------------------------
# Task 3 — chezmoi-repo in base, not in terminal; secrets not reachable from terminal
# ---------------------------------------------------------------------------

@test "profiles.toml: chezmoi-repo is a member of base" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand base | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" == *"chezmoi-repo"* ]] \
    || { echo "chezmoi-repo not found in base expansion"; return 1; }
}

@test "profiles.toml: chezmoi-repo is NOT a member of terminal" {
  run bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"
    source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_expand terminal | tr "\n" " "
  '
  [ "$status" -eq 0 ]
  [[ "$output" != *"chezmoi-repo"* ]] \
    || { echo "chezmoi-repo must NOT appear in terminal expansion"; return 1; }
}

@test "devboost list --profile terminal: secrets is NOT reachable from terminal" {
  run env DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules" \
          DEVBOOST_PROFILES="${DEVBOOST_ROOT}/profiles.toml" \
          "${DEVBOOST_ROOT}/bin/devboost" list --profile terminal
  [ "$status" -eq 0 ]
  [[ "$output" != *"secrets"* ]] \
    || { echo "secrets must NOT be reachable from terminal (transitively or directly)"; return 1; }
}
