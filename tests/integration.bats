load test_helper
@test "install then re-install is idempotent (second run all skips)" {
  work="$(mktemp -d)"; mkdir -p "$work/modules"; mark="$work/m"
  cat > "$work/modules/alpha.toml" <<EOF
name = "alpha"
[install]
default = "touch $mark.a"
verify  = "test -f $mark.a"
EOF
  cat > "$work/modules/beta.toml" <<EOF
name = "beta"
requires = ["alpha"]
[install]
default = "touch $mark.b"
verify  = "test -f $mark.b"
EOF
  printf '[profiles]\nstack=["beta"]\n' > "$work/profiles.toml"
  common=(DEVBOOST_MODULES_DIR="$work/modules" DEVBOOST_PROFILES="$work/profiles.toml"
          OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora")

  run env "${common[@]}" "$DEVBOOST_ROOT/bin/devboost" install --profile stack
  [ -f "$mark.a" ]; [ -f "$mark.b" ]

  run env "${common[@]}" "$DEVBOOST_ROOT/bin/devboost" install --profile stack
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}
