load test_helper
setup() {
  export DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules"
  export DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml"
  export OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora"
}

@test "help exits 0 and shows usage" {
  run "$DEVBOOST_ROOT/bin/devboost" help
  [ "$status" -eq 0 ]; [[ "$output" == *"Usage"* ]]
}
@test "unknown verb exits 1" {
  run "$DEVBOOST_ROOT/bin/devboost" frobnicate
  [ "$status" -eq 1 ]
}
@test "list resolves profile to ordered modules" {
  run "$DEVBOOST_ROOT/bin/devboost" list --profile full
  [ "$status" -eq 0 ]
  [[ "$output" == *"git"* ]]; [[ "$output" == *"mise"* ]]
}
@test "doctor passes on a sane host" {
  run "$DEVBOOST_ROOT/bin/devboost" doctor
  [ "$status" -eq 0 ]
}
@test "install full runs without crashing (echo modules)" {
  run "$DEVBOOST_ROOT/bin/devboost" install --profile full
  [[ "$output" == *"summary"* ]]
}
@test "bare module arg: list git shows only git module" {
  run "$DEVBOOST_ROOT/bin/devboost" list git
  [ "$status" -eq 0 ]
  [ "$output" = "git" ]
}
@test "--profile with no value exits non-zero" {
  run "$DEVBOOST_ROOT/bin/devboost" install --profile
  [ "$status" -ne 0 ]
}
