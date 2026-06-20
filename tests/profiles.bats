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
