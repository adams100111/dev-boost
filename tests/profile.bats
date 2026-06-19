load test_helper
setup() {
  load_lib log.sh; load_lib toml.sh; load_lib profile.sh
  export DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml"
}

@test "lists profile names" {
  run profile_expand   # no-op guard; ensure sourced
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"; profile_names | sort | tr "\n" " "'
  [[ "$output" == *"base"* ]]; [[ "$output" == *"full"* ]]
}

@test "expands nested profiles to flat module set" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" profile_expand full | sort | tr "\n" " "'
  [ "$status" -eq 0 ]
  [ "$output" = "bun ddev git mise " ]
}

@test "bare module token passes through" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" profile_expand docker | tr "\n" " "'
  [ "$output" = "docker " ]
}
