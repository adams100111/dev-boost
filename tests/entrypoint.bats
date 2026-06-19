load test_helper
@test "entrypoint dry-run reports deps and forwards args" {
  run env DEVBOOST_DRYRUN=1 \
      DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules" \
      DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" \
      OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora" \
      bash "$DEVBOOST_ROOT/install.sh" --profile full
  [ "$status" -eq 0 ]
  [[ "$output" == *"python3"* ]]
  [[ "$output" == *"--profile full"* ]]
}
