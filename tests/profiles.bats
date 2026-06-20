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
