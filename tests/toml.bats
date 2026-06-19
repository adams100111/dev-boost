load test_helper
setup() { load_lib log.sh; load_lib toml.sh; }

@test "converts toml to json queryable by jq" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    toml_to_json "$DEVBOOST_ROOT/tests/fixtures/sample.toml"'
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.name == "bun"'
  echo "$output" | jq -e '.install.fedora == "dnf install -y bun"'
  echo "$output" | jq -e '.requires[0] == "mise"'
}

@test "invalid toml dies non-zero" {
  tmp="$(mktemp)"; printf 'x = = =\n' > "$tmp"
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; toml_to_json "$1"' _ "$tmp"
  [ "$status" -ne 0 ]
  rm -f "$tmp"
}
